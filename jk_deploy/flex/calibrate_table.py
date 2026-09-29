#!/usr/bin/env python3
"""Build a new, checked four-camera calibration candidate without touching the DUT."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import cv2
import numpy as np
import scipy

from align_markers import DEFAULT_GEOMETRY, camera_ring, validate_marker_views
from make_lut import load_lenses

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_report(output, report):
    temp = output/"report.json.tmp"
    temp.write_text(json.dumps(report, indent=2)+"\n")
    temp.replace(output/"report.json")


def calibrate(source, output, front=0, marker_ids=None, geometry=DEFAULT_GEOMETRY, inset_percent=.5,
              deployment_policy="standalone", detected_corners=None, reference=None):
    # Never reuse a previous session, including a failed one.
    output.mkdir(parents=True, exist_ok=False)
    (output/".gitignore").write_text("/captures/\n*.png\n*.uyvy\n")
    captures = output/"captures"
    captures.mkdir()
    report = {"status": "running", "deployment_policy": deployment_policy,
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "source": str(source.resolve()), "steps": [], "inputs_sha256": {},
              "versions": {"python": sys.version, "opencv": cv2.__version__,
                           "numpy": np.__version__, "scipy": scipy.__version__}}
    def run(script, *args):
        step = {"command": [sys.executable, str(HERE/script), *map(str, args)]}
        report["steps"].append(step)
        save_report(output, report)
        with (output/"calibration.log").open("a") as log:
            log.write("\n"+repr(step["command"])+"\n")
            log.flush()
            result = subprocess.run(step["command"], stdout=log, stderr=subprocess.STDOUT, timeout=300)
        step["exit_code"] = result.returncode
        if result.returncode:
            tail = (output/"calibration.log").read_text()[-4000:]
            raise ValueError(f"{script} failed. Inspect calibration.log.\n{tail}")
    try:
        if marker_ids is not None and (len(set(marker_ids)) != 4 or any(n not in range(50) for n in marker_ids)):
            raise ValueError("Specify four distinct DICT_4X4_50 IDs in 0..49")
        shutil.copy2(geometry, output/"holder_geometry.json")
        report["source_sha256"] = {p.name: digest(p) for p in HERE.glob("*.py")}
        report["source_sha256"]["fit_intrinsics.py"] = digest(HERE.parent/"calibration/lens_20260908/fit_intrinsics.py")
        _, report["lens_sources"] = load_lenses()
        detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
        views = []
        for i in range(4):
            name = f"input{i}"
            png, raw = source/(name+".png"), source/(name+".uyvy")
            if png.is_file():
                shutil.copy2(png, captures/png.name)
                frame = cv2.imread(str(captures/png.name))
                report["inputs_sha256"][png.name] = digest(captures/png.name)
            elif raw.is_file():
                shutil.copy2(raw, captures/raw.name)
                data = np.fromfile(captures/raw.name, np.uint8)
                if data.size != 1920*1200*2:
                    raise ValueError(f"{raw.name}: expected native 1920x1200 UYVY")
                frame = cv2.cvtColor(data.reshape(1200, 1920, 2), cv2.COLOR_YUV2BGR_UYVY)
                cv2.imwrite(str(captures/(name+".png")), frame)
                report["inputs_sha256"][raw.name] = digest(captures/raw.name)
            else:
                raise ValueError(f"Missing {name}.png or {name}.uyvy in {source}")
            if frame is None or frame.shape[:2] != (1200, 1920):
                raise ValueError(f"{name}: expected native 1920x1200, without rotation/cropping")
            corners, ids, _ = detector.detectMarkers(frame)
            views.append((corners, ids, frame.shape))
        if reference is None:
            detections, report["marker_selection"] = validate_marker_views(views, marker_ids)
            order, ids, _ = camera_ring(detections, front)
            report["capture_order"] = order
            report["corner_ids_clockwise_from_front_right"] = ids
        for i in range(4):
            if detected_corners is None:
                options = [] if reference is not None else ["--marker-ids", *report["marker_selection"]["selected_ids"]]
                run("detect_table.py", captures/f"input{i}.png", *options)
            else:
                name = f"input{i}.corners.npz"
                with np.load(detected_corners/name) as data:
                    grid, points = data["grid"], data["points"]
                    if (grid.shape != points.shape or points.ndim != 2 or points.shape[1] != 2 or
                            len(points) < 150 or not np.isfinite(grid).all() or not np.isfinite(points).all() or
                            (points < 0).any() or (points > [1919, 1199]).any()):
                        raise ValueError(f"Invalid pre-detected checker coordinates: {name}")
                shutil.copy2(detected_corners/name, captures/name)
                report["inputs_sha256"][name] = digest(captures/name)
        run("fit_floor.py", output)
        if reference is None:
            options = ["--front-input", front, "--geometry", output/"holder_geometry.json",
                       "--inset-percent", inset_percent]
            options += ["--marker-ids", *report["marker_selection"]["selected_ids"]]
            run("align_markers.py", output, *options)
        else:
            from refine_clean_table import clean_config
            config = clean_config(output, reference)
            (output/"session.json").write_text(json.dumps(config, indent=2)+"\n")
            shutil.copy2(reference/"holder_geometry.json", output/"holder_geometry.json")
            for key in ("capture_order", "corner_ids_clockwise_from_front_right", "marker_selection", "clean_refinement"):
                report[key] = config[key]
        run("bake_floor.py", output)
        result = json.loads((output/"calibration.json").read_text())
        report.update(status="passed", artifact_sha256=result["sha256"],
                      crop_quality=result["crop_quality"], crop_coverage=result["crop_coverage"],
                      heldout_grid_errors=[m["heldout_grid_error"] for m in result["cameras"]])
    except (Exception, KeyboardInterrupt) as error:
        report.update(status="rejected", reason=str(error) or "Interrupted")
        # A failed candidate must not look deployable even if a late stage failed.
        for name in ("four_mesh.bin", "four_blend.bin", "camera_order.txt"):
            (output/name).unlink(missing_ok=True)
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save_report(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("captures", type=Path, help="Directory containing input0..3.png or .uyvy")
    parser.add_argument("output", type=Path, help="NEW candidate directory; existing paths are refused")
    parser.add_argument("--front-input", type=int, choices=range(4), default=0)
    parser.add_argument("--marker-ids", type=int, nargs=4, help="Optional filter for unrelated visible labels")
    parser.add_argument("--geometry", type=Path, default=DEFAULT_GEOMETRY)
    parser.add_argument("--inset-percent", type=float, default=.5)
    args = parser.parse_args()
    try:
        report = calibrate(args.captures.resolve(), args.output.resolve(), args.front_input,
                           args.marker_ids, args.geometry, args.inset_percent)
    except (Exception, KeyboardInterrupt) as error:
        parser.exit(1, f"Calibration not accepted: {error}\n")
    print(f"PASS: {args.output}/comparison.png\nNo target files changed.")
    print(f"Camera order: {report['capture_order']}; IDs clockwise: {report['corner_ids_clockwise_from_front_right']}")


if __name__ == "__main__":
    main()
