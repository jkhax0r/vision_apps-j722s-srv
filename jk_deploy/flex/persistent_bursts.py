"""Read separated native bursts through one warmed-up v4l2-ctl stream."""
from datetime import datetime, timezone
import os
import selectors
import subprocess
import time


def read_frame(stream, size, selector, timeout=45):
    frame = bytearray()
    deadline = time.monotonic()+timeout
    while len(frame) < size:
        remaining = deadline-time.monotonic()
        if remaining <= 0 or not selector.select(remaining):
            raise TimeoutError('Camera stopped delivering frames')
        data = os.read(stream.fileno(), min(size-len(frame), 1024*1024))
        if not data:
            raise ValueError(f'Camera stream ended mid-frame ({len(frame)}/{size} bytes)')
        frame.extend(data)
    return frame


def capture_bursts(command, paths, frames, frame_bytes, gap, log_path):
    observations = []
    with log_path.open('w') as log:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, bufsize=0)
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ)
        try:
            for n, path in enumerate(paths):
                started = datetime.now(timezone.utc).isoformat()
                with path.open('xb') as stream:
                    for _ in range(frames):
                        stream.write(read_frame(process.stdout, frame_bytes, selector))
                observations.append(dict(started_utc=started, finished_utc=datetime.now(timezone.utc).isoformat(),
                                         bytes=path.stat().st_size))
                if n+1 < len(paths):
                    deadline = time.monotonic()+gap
                    while time.monotonic() < deadline:
                        read_frame(process.stdout, frame_bytes, selector)
            if process.poll() is not None:
                raise RuntimeError(f'Continuous camera stream exited unexpectedly ({process.returncode})')
        finally:
            selector.close()
            if process.poll() is None:
                process.terminate()
            try:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            finally:
                process.stdout.close()
    return observations
