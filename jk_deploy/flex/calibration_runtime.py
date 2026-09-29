"""Bounded external CPU workers with timeout and failure cleanup."""
import os
from pathlib import Path
import signal
import subprocess
import time


class PreviewPause:
    """Freeze only the renderer, preserving its surface and the interactive UI."""
    def __enter__(self):
        self.pid = int(subprocess.check_output(
            ['systemctl', 'show', 'jk-flex-ti-srv.service', '-p', 'MainPID', '--value'], text=True, timeout=5).strip())
        if self.pid <= 1:
            raise ValueError('No running preview to pause')
        self.identity = self.process_identity()
        os.kill(self.pid, signal.SIGSTOP)
        return self

    def process_identity(self):
        # comm may contain spaces or parentheses; field 22 follows the last ')'.
        return (Path('/proc')/str(self.pid)/'stat').read_text().rsplit(')', 1)[1].split()[19]

    def __exit__(self, *error):
        try:
            if self.process_identity() == self.identity:
                os.kill(self.pid, signal.SIGCONT)
        except ProcessLookupError:
            pass
        except FileNotFoundError:
            pass


def available_workers(maximum=4):
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        memory[key] = int(value.strip().split()[0])
    # Reserve 512 MiB outside the pool and allow 600 MiB peak per OpenCV worker.
    budget = max(1, (memory.get('MemAvailable', 0)-512*1024)//(600*1024))
    return max(1, min(maximum, os.cpu_count() or 1, budget))


def run_commands(jobs, workers=1, threads=1):
    if not 1 <= workers <= 4 or not 1 <= threads <= 4:
        raise ValueError('Use one to four workers/threads')
    env = dict(os.environ, JK_CAL_THREADS=str(threads), OMP_NUM_THREADS=str(threads),
               OPENBLAS_NUM_THREADS='1', OPENCV_OPENCL_RUNTIME='disabled')
    waiting, active, results = iter(jobs), [], []
    exhausted = False
    try:
        while active or not exhausted:
            while len(active) < workers and not exhausted:
                try:
                    job = next(waiting)
                except StopIteration:
                    exhausted = True
                    break
                print(job['label'], flush=True)
                log = job['log'].open('w')
                try:
                    process = subprocess.Popen(list(map(str, job['command'])), stdout=log,
                                               stderr=subprocess.STDOUT, env=env)
                except BaseException:
                    log.close()
                    raise
                active.append((job, process, log, time.monotonic()))
            for entry in list(active):
                job, process, log, started = entry
                code = process.poll()
                if code is None:
                    if time.monotonic()-started > job.get('timeout', 300):
                        raise TimeoutError(f"{job['label']} timed out; inspect {job['log']}")
                    continue
                log.close()
                active.remove(entry)
                if code:
                    tail = job['log'].read_text(errors='replace')[-2000:]
                    raise RuntimeError(f"{job['label']} failed ({code}): {tail}")
                results.append(dict(label=job['label'], seconds=time.monotonic()-started))
            if active:
                time.sleep(.05)
    finally:
        for _, process, _, _ in active:
            if process.poll() is None:
                process.terminate()
        for _, process, log, _ in active:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.close()
    return results
