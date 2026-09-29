#!/usr/bin/env python3
"""Run one on-device calibration job and apply only a validated result."""
import argparse
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import selectors
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time

TOOLS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TOOLS))
from stage_table import FILES, validate_candidate
from calibration_runtime import PreviewPause, available_workers
try:
    from .capture_recovery import saved_capture_source
except ImportError:
    from capture_recovery import saved_capture_source


def sync_directory(path):
    directory = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def atomic_bytes(path, value, durable=False):
    temp = path.with_suffix(".tmp")
    with temp.open('wb') as stream:
        stream.write(value)
        if durable:
            stream.flush()
            os.fsync(stream.fileno())
    temp.replace(path)
    if durable:
        sync_directory(path.parent)


def atomic_json(path, value, durable=False):
    atomic_bytes(path, (json.dumps(value, indent=2)+"\n").encode(), durable)


def current_preset(runtime):
    result = subprocess.run(["systemctl", "show", "jk-flex-ti-srv.service", "-p", "Environment", "--value"],
                            text=True, capture_output=True, timeout=5, check=True)
    env = dict(item.split("=", 1) for item in shlex.split(result.stdout) if "=" in item)
    mesh = Path(env.get("APP_SRV_FOUR_LUT", runtime/"grid_calibration_20260929_markers/four_mesh.bin"))
    directory = mesh.parent
    if not mesh.is_file() or not (directory/"four_blend.bin").is_file():
        raise ValueError("Cannot identify a working calibration to restore")
    if (directory/"camera_order.txt").is_file():
        order = (directory/"camera_order.txt").read_text().split()
    else:
        order = ["0", "1", "2", "3"]
    if sorted(order) != ["0", "1", "2", "3"]:
        raise ValueError("Invalid previous camera order")
    return directory, " ".join(order)


def install_candidate(result, runtime, name):
    validate_candidate(result)
    destination = runtime/f"table_{name}"
    if destination.exists():
        raise FileExistsError(destination)
    temporary = Path(tempfile.mkdtemp(prefix=".cal-candidate-", dir=runtime))
    try:
        for filename in FILES:
            shutil.copy2(result/filename, temporary/filename)
        shutil.copy2(TOOLS/"run_table_candidate.sh", temporary/"run.sh")
        (temporary/"run.sh").chmod(0o755)
        validate_candidate(temporary)
        for path in temporary.iterdir():
            with path.open('rb') as stream:
                os.fsync(stream.fileno())
        sync_directory(temporary)
        temporary.rename(destination)
        sync_directory(runtime)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination/"run.sh"


def wait_for_removal(job, update, timeout=1800):
    acknowledgement = job/"corners_removed.json"
    started = time.monotonic()
    update("Remove the green corners", waiting_action="remove_corners")
    try:
        while not acknowledgement.exists():
            if time.monotonic()-started > timeout:
                raise TimeoutError("Corner-removal confirmation timed out; previous calibration retained")
            time.sleep(.25)
            update()
        if json.loads(acknowledgement.read_text()) != {"action": "corners_removed"}:
            raise ValueError("Invalid corner-removal confirmation")
    finally:
        update(waiting_action=None)


def run_job(job, runtime, support, reuse=None):
    started = time.monotonic()
    job.mkdir(parents=True, exist_ok=False)
    status = {"state": "running", "phase": "Preparing", "started_utc": datetime.now(timezone.utc).isoformat(),
              "job": str(job), "timings_seconds": {}}
    # This BSP's OpenCL compiler rejects OpenCV kernels and can stall detection.
    # Keep calibration on the CPU; the separate TI renderer still uses GLES.
    env = dict(os.environ, PYTHONPATH=str(support), PYTHONUNBUFFERED="1",
               OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="2", OPENCV_OPENCL_RUNTIME="disabled")
    def update(phase=None, **values):
        if phase:
            status["phase"] = phase
        status.update(values, elapsed_seconds=round(time.monotonic()-started, 1))
        atomic_json(job/"status.json", status)
    def command(args, phase, timeout):
        update(phase, step=phase)
        step_started = time.monotonic()
        status.setdefault("commands", []).append(list(map(str, args)))
        with (job/"job.log").open("a") as log:
            log.write("\n"+shlex.join(map(str, args))+"\n")
            log.flush()
            process = subprocess.Popen(list(map(str, args)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       env=env, start_new_session=True)
            selector = selectors.DefaultSelector()
            selector.register(process.stdout, selectors.EVENT_READ)
            pending = b""
            try:
                while selector.get_map():
                    if time.monotonic()-step_started > timeout:
                        raise TimeoutError(f"{phase} exceeded {timeout} seconds")
                    for key, _ in selector.select(timeout=.5):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        log.write(chunk.decode(errors="replace"))
                        log.flush()
                        pending += chunk
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            text = line.decode(errors="replace").strip()
                            if text.startswith(("Averaging ", "Calibrating ", "Detecting ", "Checking ", "Comparing ", "pass0")):
                                update(text)
                    update()
                code = process.wait(timeout=10)
                if code:
                    raise RuntimeError(f"{phase} failed (exit {code})")
            except BaseException:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=75)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                raise
            finally:
                selector.close()
                process.stdout.close()
                status["timings_seconds"][phase] = round(time.monotonic()-step_started, 1)
                update()
    update()
    applying = False
    committed = False
    pointer_attempted = False
    active_pointer = runtime/'active_table_calibration.json'
    latest_report = None
    resume = job/"resume_previous.sh"
    try:
        if shutil.disk_usage(job).free < 3*1024**3:
            raise ValueError("Less than 3 GiB free; archive old calibration jobs before retrying")
        preset, order = current_preset(runtime)
        status["previous_preset"] = str(preset)
        captures = saved_capture_source(reuse) if reuse is not None else job
        status['capture_source'] = str(captures)
        workers = available_workers()
        status['performance'] = dict(workers=workers, motion_mode='sampled', defer_bake=True,
                                      persistent_capture=True, pause_preview=True)
        common = ['--cache', job/'average_cache', '--motion-mode', 'sampled']
        fitting = ['--workers', str(workers), '--defer-bake', *common]
        resume.write_text("#!/bin/bash\nset -euo pipefail\nexport FLEX_CALIBRATION_DIR="+shlex.quote(str(preset))+
                          "\nexport FLEX_COMPARE=1\nexport CAMERA_ORDER="+shlex.quote(order)+
                          "\nexec "+shlex.quote(str(runtime/"run_flex_stitch.sh"))+"\n")
        resume.chmod(0o755)
        if reuse is None:
            command([sys.executable, TOOLS/"capture_table_bursts.py", job/"raw", "--runtime", runtime, "--resume", resume, '--persistent'],
                    "Capturing marked table", 600)
            latest_report = job/"marked_check.json"
            with PreviewPause():
                command([sys.executable, TOOLS/"check_calibration_markers.py", job/"raw", latest_report, *common],
                        "Checking marked table", 180)
            wait_started = time.monotonic()
            wait_for_removal(job, update)
            status["timings_seconds"]["Waiting for corner removal"] = round(time.monotonic()-wait_started, 1)
            latest_report = None
            command([sys.executable, TOOLS/"capture_table_bursts.py", job/"raw_clear", "--runtime", runtime, "--resume", resume, '--persistent'],
                    "Capturing clear table", 600)
            latest_report = job/"clear_check.json"
            with PreviewPause():
                command([sys.executable, TOOLS/"check_calibration_markers.py", job/"raw_clear", latest_report,
                         "--marked-check", job/"marked_check.json", *common], "Checking clear table", 180)
        with PreviewPause():
            latest_report = job/"marked_result/report.json"
            command([sys.executable, TOOLS/"calibrate_repeated.py", captures/"raw", job/"marked_result", *fitting],
                    "Calculating marked reference", 2400)
            latest_report = job/"result/report.json"
            command([sys.executable, TOOLS/"calibrate_repeated.py", captures/"raw_clear", job/"result",
                     "--reference", job/"marked_result", *fitting], "Refining exposed corners", 2400)
        report = json.loads((job/"result/report.json").read_text())
        warnings = report.get("motion_warnings", [])+report.get("marker_stage_motion_warnings", [])
        messages = list(report.get("refinement_warnings", []))
        coverage = report.get('coverage_warnings', [])+report.get('marker_stage_coverage_warnings', [])
        if coverage:
            status['coverage_warnings'] = list(dict.fromkeys(coverage))
            messages.append('Checker detection coverage varied between captures. Calibration accuracy checks passed.')
        if warnings:
            messages.insert(0, "Movement or scene changes detected during capture. Calibration checks passed.")
            status["motion_warning_count"] = len(warnings)
        if messages:
            status["warning"] = " ".join(dict.fromkeys(messages))
        update("Applying validated calibration")
        launcher = install_candidate(job/"result", runtime, job.name)
        previous_pointer = active_pointer.read_bytes() if active_pointer.exists() else None
        applying = True
        command([launcher], "Applying", 90)
        pointer_attempted = True
        atomic_json(active_pointer, {"launcher": str(launcher),
                    "previous_preset": str(preset), "job": str(job)}, durable=True)
        committed = True
        applying = False
        update("Calibration applied", state="complete", launcher=str(launcher))
        return 0
    except (Exception, KeyboardInterrupt) as error:
        reason = str(error) or "Cancelled"
        status['failed_stage'] = status.get('step', 'Preparing')
        if latest_report and latest_report.is_file() and not isinstance(error, KeyboardInterrupt):
            try:
                reason = json.loads(latest_report.read_text()).get("reason", reason)
            except (OSError, ValueError):
                pass
        capture_restore_failed = False
        for manifest in (job/"raw/burst_manifest.json", job/"raw_clear/burst_manifest.json"):
            if manifest.is_file():
                try:
                    capture_restore_failed |= bool(json.loads(manifest.read_text()).get("resume_error"))
                except (OSError, ValueError):
                    pass
        if applying or capture_restore_failed:
            if pointer_attempted:
                try:
                    if previous_pointer is None:
                        active_pointer.unlink(missing_ok=True)
                        sync_directory(runtime)
                    else:
                        atomic_bytes(active_pointer, previous_pointer, durable=True)
                except OSError as restore_error:
                    status['persistence_restore_error'] = str(restore_error)
            try:
                command([resume], "Restoring previous calibration", 90)
            except Exception as restore_error:
                status["restore_error"] = str(restore_error)
        if committed:
            # A completion-status write may fail after the durable boot pointer
            # is committed. Do not claim the new calibration was discarded.
            status.update(state='complete', phase='Calibration applied', launcher=str(launcher),
                          warning='Calibration is live, but saving its completion status failed.')
            print(json.dumps(status), flush=True)
            return 0
        update("Cancelled" if isinstance(error, KeyboardInterrupt) else "Calibration not applied",
               state="cancelled" if isinstance(error, KeyboardInterrupt) else "failed", reason=reason, waiting_action=None)
        return 1
    finally:
        status["finished_utc"] = datetime.now(timezone.utc).isoformat()
        try:
            update()
        except OSError as error:
            print(f'Could not save final calibration status: {error}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("job", type=Path)
    parser.add_argument("--runtime", type=Path, default=Path("/opt/jk-ti-srv-flex"))
    parser.add_argument("--support", type=Path, required=True)
    parser.add_argument("--reuse", type=Path, help="Reprocess an existing complete two-stage job without capturing")
    args = parser.parse_args()
    def interrupt(signum, frame):
        raise KeyboardInterrupt("Cancelled")
    signal.signal(signal.SIGTERM, interrupt)
    with (args.runtime/"calibration.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.exit(1, "Another calibration is already running\n")
        sys.exit(run_job(args.job, args.runtime, args.support, args.reuse))


if __name__ == "__main__":
    main()
