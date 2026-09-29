#!/usr/bin/env python3
"""Capture independent native UYVY bursts on the Flex; standard library only."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import signal
import subprocess
import time

FRAME_BYTES = 1920*1200*2


def utc():
    return datetime.now(timezone.utc).isoformat()


def capture(destination, runtime, passes=3, frames=12, warmup=60, gap=1., resume=None):
    if not 3 <= passes <= 5 or not 6 <= frames <= 32 or not 0 <= warmup <= 300 or not 0 <= gap <= 30:
        raise ValueError("Use 3..5 passes, 6..32 frames, 0..300 warmup frames, and a 0..30 second gap")
    if not runtime.joinpath("run_flex_stitch.sh").is_file():
        raise ValueError("Missing Flex runtime")
    if resume and not resume.is_file():
        raise ValueError(f"Missing resume launcher: {resume}")
    destination.mkdir(parents=True, exist_ok=False)
    (destination/".gitignore").write_text("*.uyvy\n")
    required = passes*4*frames*FRAME_BYTES + 256*1024**2
    if shutil.disk_usage(destination).free < required:
        raise ValueError(f"Need at least {required/1024**2:.0f} MiB free")
    manifest = {"schema_version": 1, "status": "capturing", "started_utc": utc(),
                "width": 1920, "height": 1200, "format": "UYVY", "frames_per_burst": frames,
                "warmup_frames": warmup, "gap_seconds": gap, "passes": [], "commands": []}
    def run(command, log=None, timeout=45):
        manifest["commands"].append(list(map(str, command)))
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, check=False, timeout=timeout)
        if log:
            log.write_text(result.stdout)
        if result.returncode:
            raise RuntimeError(f"Command failed: {command}\n{result.stdout[-2000:]}")
        return result.stdout
    stopped = False
    try:
        stopped = True
        run([str(runtime/"run_flex_stitch.sh"), "stop"])
        run(["env", "CAM_WIDTH=1920", "CAM_HEIGHT=1200", str(runtime/"run_flex_four.sh"), "configure"],
            destination/"configure.log")
        run(["media-ctl", "-d", "/dev/media0", "-p"], destination/"topology.txt")
        for p in range(passes):
            directory = destination/f"pass{p+1:02d}"
            directory.mkdir()
            item = {"directory": directory.name, "started_utc": utc(), "inputs": []}
            manifest["passes"].append(item)
            for i in range(4):
                device = run(["media-ctl", "-d", "/dev/media0", "-e",
                              f"30102000.ticsi2rx context {i+1}"]).strip()
                raw = directory/f"input{i}.uyvy"
                run(["v4l2-ctl", "-d", device, "--get-fmt-video"], directory/f"input{i}.format.txt")
                started = utc()
                run(["v4l2-ctl", "-d", device, "--stream-mmap=4", f"--stream-skip={warmup}",
                     f"--stream-count={frames}", f"--stream-to={raw}"], directory/f"input{i}.capture.log")
                if raw.stat().st_size != frames*FRAME_BYTES:
                    raise ValueError(f"Input {i}: incomplete burst or unexpected stride/format")
                item["inputs"].append({"input": i, "device": device, "started_utc": started,
                                       "finished_utc": utc(), "bytes": raw.stat().st_size})
                print(f"{directory.name}: input {i}, {frames} frames", flush=True)
            item["finished_utc"] = utc()
            if p+1 < passes:
                time.sleep(gap)
        manifest["status"] = "complete"
    except BaseException as error:
        manifest.update(status="failed", reason=str(error) or type(error).__name__)
        raise
    finally:
        manifest["finished_utc"] = utc()
        try:
            if stopped and resume:
                run([str(resume)], destination/"resume.log", timeout=60)
                manifest["resumed_with"] = str(resume)
        except BaseException as error:
            manifest["resume_error"] = str(error) or type(error).__name__
            raise
        finally:
            (destination/"burst_manifest.json").write_text(json.dumps(manifest, indent=2)+"\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--runtime", type=Path, default=Path("/opt/jk-ti-srv-flex"))
    parser.add_argument("--passes", type=int, default=3)
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--warmup", type=int, default=60)
    parser.add_argument("--gap", type=float, default=1.)
    parser.add_argument("--resume", type=Path, help="Existing launcher to restore, including on capture failure")
    args = parser.parse_args()
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    try:
        capture(args.output, args.runtime, args.passes, args.frames, args.warmup, args.gap, args.resume)
    except (Exception, KeyboardInterrupt) as error:
        parser.exit(1, f"Capture failed: {error}\n")
    print(f"Complete: {args.output}; keep the raw bursts for diagnosis.")


if __name__ == "__main__":
    main()
