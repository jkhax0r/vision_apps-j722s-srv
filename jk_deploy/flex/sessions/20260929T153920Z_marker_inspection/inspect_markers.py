#!/usr/bin/env python3
"""Record default ArUco detections for this saved case; no calibration changes."""
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent


def main():
    detector = cv2.aruco.ArucoDetector(
        cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
    records, tiles = [], []
    visibility = {str(i): [] for i in range(1, 5)}
    for i in range(4):
        image = cv2.imread(str(ROOT / "captures" / f"input{i}.png"))
        if image is None:
            raise ValueError(f"Missing camera {i+1}")
        corners, ids, rejected = detector.detectMarkers(image)
        markers = []
        for points, marker_id in zip(corners, [] if ids is None else ids.ravel()):
            xy = points[0]
            marker_id = int(marker_id)
            sides = np.linalg.norm(xy-np.roll(xy, -1, axis=0), axis=1)
            markers.append({"id": marker_id, "corners": xy.tolist(),
                            "side_lengths_px": sides.astype(float).tolist()})
            visibility.setdefault(str(marker_id), []).append(i+1)
        cv2.aruco.drawDetectedMarkers(image, corners, ids)
        tile = np.zeros((654, 960, 3), np.uint8)
        tile[54:] = cv2.resize(image, (960, 600), interpolation=cv2.INTER_AREA)
        label = ", ".join(str(m["id"]) for m in sorted(markers, key=lambda m: m["id"]))
        cv2.putText(tile, f"CAM {i+1} / marker IDs {label}", (18, 36),
                    cv2.FONT_HERSHEY_SIMPLEX, .85, (255, 255, 255), 2)
        tiles.append(tile)
        record = {"camera": i+1, "capture_input": i, "markers": markers,
                  "rejected_candidates": len(rejected)}
        corner_path = ROOT / "captures" / f"input{i}.corners.npz"
        if corner_path.exists():
            with np.load(corner_path) as data:
                record["legacy_checker_detection"] = {"status": "passed", "corners": len(data["points"])}
        else:
            record["legacy_checker_detection"] = {"status": "no_saved_detection"}
        records.append(record)
    result = {"purpose": "Static inspection only, not a new calibration",
              "opencv_version": cv2.__version__, "dictionary": "DICT_4X4_50",
              "detector_settings": "OpenCV defaults; native 1920x1200 input",
              "marker_visibility": visibility, "cameras": records}
    (ROOT / "inspection.json").write_text(json.dumps(result, indent=2)+"\n")
    cv2.imwrite(str(ROOT / "marker_contact.png"),
                np.vstack((np.hstack(tiles[:2]), np.hstack(tiles[2:]))))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
