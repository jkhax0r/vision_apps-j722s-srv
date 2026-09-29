#!/usr/bin/env python3
"""Align observed checker grids and bake a floor-only TI mesh and preview."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from scipy.interpolate import CloughTocher2DInterpolator

from fit_floor import project, rotations, transform, undistort


def align(fits, config):
    anchors = {}
    models = []
    for i, fit in enumerate(fits):
        markers = {name: np.array(fit["colors"][name][index]["grid"])
                   for name, index in config["marker_candidates"][i].items()}
        if i == 0:
            rotation, shift, score = np.eye(2, dtype=int), np.zeros(2, dtype=int), 0.
        else:
            shared = sorted(set(markers) & set(anchors))
            if len(shared) < 2:
                raise ValueError(f"Camera {i+1} needs two identified anchors")
            a = np.array([markers[name] for name in shared])
            b = np.array([anchors[name] for name in shared])
            choices = []
            for r in rotations():
                s = np.rint(np.mean(b - a @ r.T, axis=0)).astype(int)
                score = float(np.sqrt(np.mean(np.sum((a @ r.T + s - b) ** 2, axis=1))))
                choices.append((score, r, s))
            choices.sort(key=lambda c: c[0])
            score, rotation, shift = choices[0]
            if score > .4 or choices[1][0] - score < .3:
                raise ValueError(f"Camera {i+1} marker alignment ambiguous: {score}")
        for name, local in markers.items():
            anchors.setdefault(name, local @ rotation.T + shift)
        models.append(dict(input=i, rotation=rotation.tolist(), shift=shift.tolist(),
                           marker_rms_cells=score))
    return models


class FloorCamera:
    def __init__(self, session, model, fitted_h=None):
        self.model = model
        self.image = cv2.imread(str(session / "captures" / f"input{model['input']}.png"))
        data = np.load(session / "captures" / f"input{model['input']}.floor.npz")
        self.grid = data["grid"] @ np.array(model["rotation"]).T + model["shift"]
        self.points = data["points"]
        if fitted_h is None:
            self.h, _ = cv2.findHomography(self.grid, undistort(self.points), cv2.RANSAC, .008)
        else:
            self.h = np.asarray(fitted_h, float)
            if self.h.shape != (3, 3) or not np.isfinite(self.h).all():
                raise ValueError("Invalid saved floor homography")
        base = self.base(self.grid)
        residual = self.points - base
        keep = np.linalg.norm(residual, axis=1) < 10
        self.grid, self.points = self.grid[keep], self.points[keep]
        self.residual = CloughTocher2DInterpolator(self.grid, residual[keep], fill_value=0.)
        self.model["corners"] = len(self.grid)
        self.model["grid_bounds"] = [self.grid.min(0).tolist(), self.grid.max(0).tolist()]
        self.model["H_global_to_undistorted"] = self.h.tolist()
        self.model["base_rms_px"] = float(np.sqrt(np.mean(np.sum(residual[keep] ** 2, axis=1))))

    def base(self, world):
        return project(np.c_[transform(world, self.h), np.ones(len(world))])

    def map(self, world):
        pixels = self.base(world) + self.residual(world)
        valid = np.isfinite(pixels).all(1) & (pixels >= 0).all(1) & (pixels <= [1919, 1199]).all(1)
        return np.clip(np.nan_to_num(pixels), 0, [1919, 1199]) + .5, valid

    def validation(self):
        hold = (np.rint(self.grid[:, 0] * 3 + self.grid[:, 1] * 5).astype(int) % 11) == 0
        h, _ = cv2.findHomography(self.grid[~hold], undistort(self.points[~hold]), 0)
        def base(points):
            return project(np.c_[transform(points, h), np.ones(len(points))])
        residual = CloughTocher2DInterpolator(self.grid[~hold], self.points[~hold] - base(self.grid[~hold]))
        predicted = base(self.grid[hold]) + residual(self.grid[hold])
        errors = np.linalg.norm(predicted - self.points[hold], axis=1)
        errors = errors[np.isfinite(errors)]
        if len(errors) < 30:
            raise ValueError("Insufficient held-out corners")
        result = {"points": len(errors), "rms_px": float(np.sqrt(np.mean(errors ** 2))),
                  "p95_px": float(np.percentile(errors, 95))}
        if result["rms_px"] > 4 or result["p95_px"] > 8:
            raise ValueError(f"Held-out grid fit failed: {result}")
        return result


def screen_plane(uv, config):
    x, y, w, h = config["crop_cells"]
    # The right pane is 960x720; preserve square-cell geometry with side margins.
    cell_pixels = min(960 / w, 720 / h)
    extent = np.array([960, 720]) / cell_pixels
    world = (uv - .5) * extent + [x + w / 2, y + h / 2]
    inside = ((world >= [x, y]) & (world <= [x + w, y + h])).all(1)
    return world, inside


def screen_world(uv, config):
    plane, inside = screen_plane(uv, config)
    frame = config.get("view_frame")
    if frame:
        plane = plane @ np.asarray(frame["axes"]).T + frame["origin_cells"]
    return plane, inside


def mapping(uv, quadrant, cameras, config):
    world, inside = screen_world(uv, config)
    source, valid = [], []
    slots = [quadrant, (quadrant + 3) % 4]
    for slot in slots:
        p, ok = cameras[slot].map(world)
        source.append(p)
        valid.append(ok)
    x, y, w, h = config["crop_cells"]
    plane, _ = screen_plane(uv, config)
    delta = plane - [x + w / 2, y + h / 2]
    axes = [-delta[:, 1], delta[:, 0], delta[:, 1], -delta[:, 0]]
    a = np.clip(.5 + (axes[slots[0]] - axes[slots[1]]) / config["feather_cells"], 0, 1)
    a = np.where(~valid[1], 1, a)
    a = np.where(~valid[0], 0, a)
    weights = np.c_[a, 1 - a]
    weights[~inside | ~(valid[0] | valid[1])] = 0
    return source, weights


def coverage(cameras, config):
    covered, total = 0, 0
    for q in range(4):
        col, row = np.meshgrid((np.arange(120)+.5)/120, (np.arange(90)+.5)/90)
        uv = np.c_[col.ravel(), row.ravel()]*.5 + [0 if q in (0, 3) else .5, 0 if q < 2 else .5]
        _, inside = screen_world(uv, config)
        _, weights = mapping(uv, q, cameras, config)
        total += int(inside.sum())
        covered += int((inside & (weights.sum(1) > 0)).sum())
    fraction = covered/max(total, 1)
    if fraction < .985:
        raise ValueError(f"Only {fraction:.1%} of the proposed crop has camera coverage; adjust aim/crop")
    return {"sampled_pixels": total, "covered_fraction": fraction}


def preview(cameras, config, path):
    output = np.zeros((720, 960, 3), np.uint8)
    for q in range(4):
        x0, y0 = (0 if q in (0, 3) else 480), (0 if q < 2 else 360)
        col, row = np.meshgrid(np.arange(x0, x0+480), np.arange(y0, y0+360))
        uv = np.c_[col.ravel()+.5, row.ravel()+.5] / [960, 720]
        source, weights = mapping(uv, q, cameras, config)
        value = np.zeros((360, 480, 3), float)
        for j, slot in enumerate((q, (q+3) % 4)):
            coords = (source[j] - .5).astype(np.float32).reshape(360, 480, 2)
            sampled = cv2.remap(cameras[slot].image, coords, None, cv2.INTER_LINEAR)
            value += sampled * weights[:, j].reshape(360, 480, 1)
        output[y0:y0+360, x0:x0+480] = np.clip(value, 0, 255).astype(np.uint8)
    cv2.imwrite(str(path / "stitched.png"), output)
    left = np.zeros_like(output)
    for i, camera in enumerate(cameras):
        x, y = (i % 2)*480, (i // 2)*360 + 30
        left[y:y+300, x:x+480] = cv2.resize(camera.image, (480, 300), interpolation=cv2.INTER_AREA)
        cv2.putText(left, f"CAM {i+1}", (x+12, y-8), cv2.FONT_HERSHEY_SIMPLEX, .55, (255, 255, 255), 1)
    cv2.imwrite(str(path / "comparison.png"), np.hstack((left, output)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    args = parser.parse_args()
    config = json.loads((args.session / "session.json").read_text())
    if "aligned_models" in config:
        models = config["aligned_models"]
        if [m["input"] for m in models] != list(range(4)):
            raise ValueError("Aligned models must be in camera input order 0,1,2,3")
    else:
        models = align(json.loads((args.session / "floor_fits.json").read_text()), config)
    order = config.get("capture_order", list(range(4)))
    if sorted(order) != list(range(4)):
        raise ValueError("Capture order must be a permutation of 0,1,2,3")
    cameras = [FloorCamera(args.session, models[i]) for i in order]
    for camera in cameras:
        camera.model["heldout_grid_error"] = camera.validation()
    crop_coverage = coverage(cameras, config)
    meshes, blends = [], []
    for q in range(4):
        col, row = np.meshgrid(np.linspace(0, 1, 136), np.linspace(0, 1, 136))
        uv = np.c_[col.ravel(), row.ravel()] * .5 + [0 if q in (0, 3) else .5, 0 if q < 2 else .5]
        source, weights = mapping(uv, q, cameras, config)
        entry = np.zeros((len(uv), 7), dtype="<i2")
        entry[:, 0] = np.rint(uv[:, 0]*1080 - 540)
        # Native imported RGBX framebuffer presentation has reversed Y.
        entry[:, 1] = np.rint(uv[:, 1]*1080 - 540)
        for offset, pixels in zip((3, 5), source):
            entry[:, offset] = np.rint(pixels[:, 1] * 16)
            entry[:, offset+1] = np.rint(pixels[:, 0] * 16)
        a = np.rint(weights[:, 0] * 255).astype(np.uint8)
        b = np.where(weights.sum(1) > 0, 255-a, 0).astype(np.uint8)
        meshes.append(entry)
        blends.append(np.c_[a, b])
    mesh, blend = np.concatenate(meshes), np.concatenate(blends)
    assert mesh.shape == (4*136*136, 7) and blend.shape == (4*136*136, 2)
    assert np.all((blend.sum(1) == 0) | (blend.sum(1) == 255))
    mesh.tofile(args.session / "four_mesh.bin")
    blend.tofile(args.session / "four_blend.bin")
    result = dict(config, cameras=models, capture_order=order, crop_coverage=crop_coverage, comparison_layout=True,
                  method="Shared lens prior + observed checker-plane homographies and smooth residuals",
                  limitation="Floor-only mapping, not new lens intrinsics or general 3D reconstruction")
    result["sha256"] = {name: hashlib.sha256((args.session / name).read_bytes()).hexdigest()
                        for name in ("four_mesh.bin", "four_blend.bin")}
    (args.session / "calibration.json").write_text(json.dumps(result, indent=2) + "\n")
    (args.session / "camera_order.txt").write_text(" ".join(map(str, order))+"\n")
    preview(cameras, config, args.session)
    print(json.dumps(models, indent=2), flush=True)


if __name__ == "__main__":
    main()
