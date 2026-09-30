"""Bound calibration storage. Caller must hold the runtime calibration lock."""
import json
import os
from pathlib import Path
import re
import shutil

JOB_NAME = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{6}')


def cleanup_calibrations(jobs, runtime, current_preset, protect=()):
    jobs, runtime = Path(jobs).resolve(), Path(runtime).resolve()
    protected = {Path(p).resolve() for p in protect}
    presets = {Path(current_preset).resolve()}
    pointer = runtime/'active_table_calibration.json'
    retained_jobs = set()
    if pointer.exists():
        active = json.loads(pointer.read_text())
        presets.add(Path(active['launcher']).resolve().parent)
        presets.add(Path(active['previous_preset']).resolve())
        retained_jobs.add(Path(active['job']).resolve())
    if any(p.parent != runtime for p in presets):
        raise ValueError('Calibration cleanup refused an external preset')
    if any(p.parent != jobs for p in retained_jobs | protected):
        raise ValueError('Calibration cleanup refused an external job')
    for preset in presets:
        if preset.name.startswith('table_') and JOB_NAME.fullmatch(preset.name[6:]):
            retained_jobs.add(jobs/preset.name[6:])

    candidates = []
    for job in jobs.iterdir():
        if not JOB_NAME.fullmatch(job.name) or job.is_symlink() or not job.is_dir() or job in protected:
            continue
        if job in retained_jobs:
            # Installed presets are self-contained; raw frames are not needed to boot.
            candidates.extend(p for p in job.iterdir() if p.name not in ('status.json', 'job.log'))
        else:
            candidates.append(job)
    for preset in runtime.iterdir():
        if (preset.name.startswith('table_') and JOB_NAME.fullmatch(preset.name[6:])
                and not preset.is_symlink() and preset.is_dir() and preset not in presets):
            candidates.append(preset)

    # Validate the entire deletion plan before removing anything. Never cross mounts.
    for candidate in candidates:
        device = candidate.parent.stat().st_dev
        for base, directories, files in os.walk(candidate, followlinks=False) if not candidate.is_symlink() else ():
            for path in [Path(base), *(Path(base)/n for n in directories + files)]:
                if not path.is_symlink() and (path.is_mount() or path.stat().st_dev != device):
                    raise ValueError(f'Calibration cleanup refused mounted path: {path}')
    before = shutil.disk_usage(jobs).free
    removed, errors = [], []
    for path in candidates:
        try:
            if path.is_symlink() or not path.is_dir():
                path.unlink()
            else:
                shutil.rmtree(path)
            removed.append(str(path))
        except OSError as error:
            errors.append(f'{path}: {error}')
    return dict(removed=removed, errors=errors,
                freed_bytes=max(0, shutil.disk_usage(jobs).free-before))
