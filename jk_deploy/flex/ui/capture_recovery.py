"""Check that a completed two-stage capture can be retried without camera access."""
import json
from pathlib import Path


def saved_capture_source(job):
    job = Path(job).resolve()
    status = json.loads((job/'status.json').read_text())
    if not isinstance(status, dict):
        raise ValueError('Invalid saved job status')
    source = Path(status.get('capture_source', job)).resolve()
    if source.parent != job.parent:
        raise ValueError('Saved capture must belong to the same jobs directory')
    if json.loads((source/'corners_removed.json').read_text()) != {'action': 'corners_removed'}:
        raise ValueError('Second capture was not confirmed')
    for name in ('marked_check.json', 'clear_check.json'):
        report = json.loads((source/name).read_text())
        if not isinstance(report, dict) or report.get('passed') is not True:
            raise ValueError('Both marker checks must have passed')
    for stage in ('raw', 'raw_clear'):
        directory = source/stage
        if not directory.resolve().is_relative_to(source):
            raise ValueError('Capture directory is outside this job')
        manifest = json.loads((directory/'burst_manifest.json').read_text())
        if not isinstance(manifest, dict):
            raise ValueError('Invalid capture manifest')
        count = manifest.get('frames_per_burst')
        if (manifest.get('schema_version') != 1 or manifest.get('status') != 'complete' or
                manifest.get('simulated_input') or type(count) is not int or not 6 <= count <= 32 or
                (manifest.get('width'), manifest.get('height'), manifest.get('format')) != (1920, 1200, 'UYVY')):
            raise ValueError('Incomplete or unsupported saved capture')
        passes = manifest.get('passes')
        if not isinstance(passes, list) or any(not isinstance(p, dict) for p in passes):
            raise ValueError('Invalid capture passes')
        names = [p.get('directory') for p in passes]
        if not 3 <= len(names) <= 5 or names != [f'pass{i+1:02d}' for i in range(len(names))]:
            raise ValueError('Incomplete capture passes')
        for name in names:
            for i in range(4):
                raw = directory/name/f'input{i}.uyvy'
                if not raw.resolve().is_relative_to(source) or raw.stat().st_size != count*1920*1200*2:
                    raise ValueError('Saved camera frames are missing or truncated')
    return source
