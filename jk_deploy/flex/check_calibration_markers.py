"""Check averaged corner markers before prompting or beginning the expensive fit."""
import argparse
import json
from pathlib import Path

import cv2

from align_markers import camera_ring, validate_marker_views
from average_burst import average_raw
from calibrate_repeated import validate_manifest


def check(source, output, marked_check=None):
    manifest = json.loads((source/'burst_manifest.json').read_text())
    passes, count = validate_manifest(manifest)
    detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    views = []
    for i in range(4):
        print(f'Checking corner markers: camera {i+1}', flush=True)
        frame, _ = average_raw(source/passes[0]/f'input{i}.uyvy', count)
        corners, ids, _ = detector.detectMarkers(frame)
        views.append((corners, ids, frame.shape))
    if marked_check is None:
        pixels, selection = validate_marker_views(views)
        order, ids, _ = camera_ring(pixels)
        result = dict(marker_selection=selection, capture_order=order, corner_ids=ids)
    else:
        expected = set(json.loads(marked_check.read_text())['marker_selection']['selected_ids'])
        for i, (_, ids, _) in enumerate(views):
            remaining = expected & (set(map(int, ids.ravel())) if ids is not None else set())
            if remaining:
                raise ValueError(f'Camera {i+1}: corner markers {sorted(remaining)} are still visible. Remove all four green holders.')
        result = dict(markers_removed=True)
    result['passed'] = True
    output.write_text(json.dumps(result, indent=2)+'\n')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--marked-check', type=Path)
    args = parser.parse_args()
    try:
        check(args.source, args.output, args.marked_check)
    except Exception as error:
        args.output.write_text(json.dumps({'passed': False, 'reason': str(error)}, indent=2)+'\n')
        parser.exit(1, f'Marker check failed: {error}\n')


if __name__ == '__main__':
    main()
