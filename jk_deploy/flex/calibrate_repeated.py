#!/usr/bin/env python3
"""Average bursts with motion warnings, fit every pass, and validate calibrations."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import traceback

import cv2

from align_markers import DEFAULT_GEOMETRY, validate_marker_views
from average_burst import average_raw, motion_diagnostic
from calibrate_table import HERE, calibrate, digest, save_report
from repeat_consistency import common_checker_support, compare_sessions


def validate_manifest(manifest):
    if (manifest.get("schema_version") != 1 or manifest.get("status") != "complete" or
            (manifest.get("width"), manifest.get("height"), manifest.get("format")) != (1920, 1200, "UYVY")):
        raise ValueError("Need a complete native 1920x1200 UYVY burst capture")
    count = manifest.get("frames_per_burst")
    if not isinstance(count, int) or not 6 <= count <= 32:
        raise ValueError("Need 6..32 frames per burst")
    passes = [item["directory"] for item in manifest["passes"]]
    if not 3 <= len(passes) <= 5 or len(set(passes)) != len(passes):
        raise ValueError("Need three to five separate passes")
    if any(not re.fullmatch(r"pass[0-9]{2}", name) for name in passes):
        raise ValueError("Invalid pass directory name")
    return passes, count


def calibrate_bursts(source, output, front=0, marker_ids=None, geometry=DEFAULT_GEOMETRY, inset_percent=.5, reference=None):
    output.mkdir(parents=True, exist_ok=False)
    (output/".gitignore").write_text("*.png\n*.uyvy\n/captures/\n/prepared/\n")
    report = {"status": "running", "deployment_policy": "repeat-confirmed",
              "started_utc": datetime.now(timezone.utc).isoformat(), "source": str(source.resolve()),
              "raw_sha256": {}, "bursts": [], "between_pass_motion": [],
              "motion_policy": "warn_only", "motion_warnings": []}
    try:
        manifest = json.loads((source/"burst_manifest.json").read_text())
        names, count = validate_manifest(manifest)
        report["simulated_input"] = bool(manifest.get("simulated_input", False))
        shutil.copy2(source/"burst_manifest.json", output/"burst_manifest.json")
        report["capture_manifest_sha256"] = digest(output/"burst_manifest.json")
        for p, name in enumerate(names):
            prepared = output/"prepared"/name
            prepared.mkdir(parents=True)
            for i in range(4):
                raw = source/name/f"input{i}.uyvy"
                print(f"Averaging {name}, input {i} ({count} frames)", flush=True)
                report["raw_sha256"][f"{name}/{raw.name}"] = digest(raw)
                try:
                    image, quality = average_raw(raw, count)
                except ValueError as error:
                    raise ValueError(f"Camera {i+1}, {name}: {error}") from error
                cv2.imwrite(str(prepared/f"input{i}.png"), image)
                report["bursts"].append(dict(pass_number=p+1, input=i, **quality))
                for observation in quality["motion"]:
                    if observation.get("warning"):
                        report["motion_warnings"].append(dict(pass_number=p+1, input=i, **observation))
                for previous in names[:p]:
                    previous_image = cv2.imread(str(output/"prepared"/previous/f"input{i}.png"))
                    motion = motion_diagnostic(previous_image, image)
                    report["between_pass_motion"].append(dict(reference=previous, candidate=name, input=i, **motion))
                    if motion.get("warning"):
                        report["motion_warnings"].append(dict(reference=previous, candidate=name, input=i, **motion))
                save_report(output, report)
        for name in names:
            detection_options = []
            if reference is None:
                detector = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50))
                views = []
                for i in range(4):
                    image = cv2.imread(str(output/"prepared"/name/f"input{i}.png"))
                    corners, ids, _ = detector.detectMarkers(image)
                    views.append((corners, ids, image.shape))
                _, selection = validate_marker_views(views, marker_ids)
                detection_options = ["--marker-ids", *map(str, selection["selected_ids"])]
            for i in range(4):
                print(f"Detecting checkerboard: {name}, input {i}", flush=True)
                image = output/"prepared"/name/f"input{i}.png"
                command = [sys.executable, str(HERE/"detect_table.py"), str(image), *detection_options]
                with image.with_suffix(".detect.log").open("w") as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=300)
        print("Checking common checker coverage", flush=True)
        report["common_checker_support"] = common_checker_support([output/"prepared"/name for name in names])
        save_report(output, report)
        sessions = []
        for name in names:
            session = output/"passes"/name
            sessions.append(session)
            print(f"Calibrating {name} independently", flush=True)
            calibrate(output/"prepared"/name, session, front, marker_ids, geometry, inset_percent,
                      deployment_policy="repeat-child", detected_corners=output/"prepared"/name, reference=reference)
        print("Comparing calibration passes", flush=True)
        consistency = compare_sessions(sessions)
        report["repeat_consistency"] = consistency
        if not consistency["passed"]:
            reasons = [reason for pair in consistency["pairs"] for reason in pair["reasons"]]
            raise ValueError("Independent fits disagree: "+"; ".join(reasons))
        selected = sessions[consistency["selected_pass"]-1]
        selected_report = json.loads((selected/"report.json").read_text())
        for name in ("four_mesh.bin", "four_blend.bin", "calibration.json", "session.json", "floor_fits.json",
                     "holder_geometry.json", "camera_order.txt", "comparison.png", "stitched.png"):
            shutil.copy2(selected/name, output/name)
        shutil.copytree(selected/"captures", output/"captures")
        for key in ("artifact_sha256", "capture_order", "corner_ids_clockwise_from_front_right", "marker_selection", "crop_quality",
                    "crop_coverage", "heldout_grid_errors", "versions", "lens_sources", "source_sha256"):
            report[key] = selected_report[key]
        if reference is not None:
            report["clean_refinement"] = selected_report["clean_refinement"]
            report["clean_refinement_passes"] = [json.loads((s/"report.json").read_text())["clean_refinement"] for s in sessions]
            reference_report = json.loads((reference/"report.json").read_text())
            report["marker_stage_motion_warnings"] = reference_report.get("motion_warnings", [])
            report["simulated_input"] |= bool(reference_report.get("simulated_input", False))
            report["refinement_warnings"] = [c["warning"] for c in report["clean_refinement"]["cameras"] if c["warning"]]
            if not any(c["new_checker_intersections"] for c in report["clean_refinement"]["cameras"]):
                report["refinement_warnings"].append("No new checker intersections were detected after marker removal.")
        report.update(status="passed", selected_session=str(selected.relative_to(output)),
                      aggregation="Average within each burst; keep the most representative independently validated pass. No image registration.")
    except (Exception, KeyboardInterrupt) as error:
        report.update(status="rejected", reason=str(error) or "Interrupted")
        for name in ("four_mesh.bin", "four_blend.bin", "camera_order.txt"):
            (output/name).unlink(missing_ok=True)
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        save_report(output, report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bursts", type=Path)
    parser.add_argument("output", type=Path, help="NEW directory; existing sessions cannot be overwritten")
    parser.add_argument("--front-input", type=int, choices=range(4), default=0)
    parser.add_argument("--marker-ids", type=int, nargs=4)
    parser.add_argument("--geometry", type=Path, default=DEFAULT_GEOMETRY)
    parser.add_argument("--inset-percent", type=float, default=.5)
    parser.add_argument("--reference", type=Path, help="Passed marked-stage result; refine without markers using its coordinate frame/crop")
    args = parser.parse_args()
    try:
        result = calibrate_bursts(args.bursts.resolve(), args.output.resolve(), args.front_input,
                                  args.marker_ids, args.geometry, args.inset_percent, args.reference)
    except (Exception, KeyboardInterrupt) as error:
        traceback.print_exc()
        parser.exit(1, f"Repeated calibration not accepted: {error}\n")
    print(f"PASS: {args.output}/comparison.png; selected pass {result['repeat_consistency']['selected_pass']}. "
          "No target calibration changed.")


if __name__ == "__main__":
    main()
