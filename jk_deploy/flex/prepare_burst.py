#!/usr/bin/env python3
"""Prepare a burst once; validate content-addressed caches before reusing them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

import cv2
import numpy as np

import average_burst


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            value.update(chunk)
    return value.hexdigest()


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def prepared_burst(raw, count, cache=None, motion_mode='all'):
    started = time.monotonic()
    raw = Path(raw)
    if not 6 <= count <= 32 or raw.stat().st_size != count*average_burst.FRAME_BYTES:
        raise ValueError(f'Wrong raw burst length: {raw}')
    identity = dict(schema_version=1, raw_sha256=digest(raw), frames=count, motion_mode=motion_mode,
                    algorithm_sha256=digest(Path(average_burst.__file__)), opencv=cv2.__version__, numpy=np.__version__)
    key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    metadata = dict(identity, cache_hit=False)
    if cache is not None:
        png, report = Path(cache)/(key+'.png'), Path(cache)/(key+'.json')
        try:
            saved = json.loads(report.read_text())
            payload = png.read_bytes()
            quality = saved['quality']
            if (saved['identity'] == identity and hashlib.sha256(payload).hexdigest() == saved['image_sha256']
                    and hashlib.sha256(json.dumps(quality, sort_keys=True).encode()).hexdigest() == saved['quality_sha256']
                    and quality['frames'] == count and quality['motion_mode'] == motion_mode):
                image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
                if image is not None and image.shape == (1200, 1920, 3):
                    return image, quality, dict(metadata, cache_hit=True, seconds=time.monotonic()-started)
        except (OSError, ValueError, KeyError, TypeError, cv2.error):
            pass
    image, quality = average_burst.average_raw(raw, count, motion_mode)
    if cache is not None:
        ok, encoded = cv2.imencode('.png', image)
        if not ok:
            raise ValueError('Could not encode averaged image')
        payload = encoded.tobytes()
        saved = dict(identity=identity, image_sha256=hashlib.sha256(payload).hexdigest(), quality=quality,
                     quality_sha256=hashlib.sha256(json.dumps(quality, sort_keys=True).encode()).hexdigest())
        atomic_write(png, payload)
        atomic_write(report, (json.dumps(saved, indent=2)+'\n').encode())
    return image, quality, dict(metadata, seconds=time.monotonic()-started)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--frames', type=int, required=True)
    parser.add_argument('--cache', type=Path)
    parser.add_argument('--motion-mode', choices=('all', 'sampled'), default='all')
    args = parser.parse_args()
    cv2.setNumThreads(int(os.environ.get('JK_CAL_THREADS', '4')))
    image, quality, metadata = prepared_burst(args.raw, args.frames, args.cache, args.motion_mode)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(args.output), image):
        raise ValueError('Could not save averaged image')
    atomic_write(args.output.with_suffix('.average.json'),
                 (json.dumps(dict(quality=quality, metadata=metadata), indent=2)+'\n').encode())


if __name__ == '__main__':
    main()
