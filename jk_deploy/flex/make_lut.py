#!/usr/bin/env python3
"""Approximate four-identical-camera ground mapping for TI's existing GPU node.

The shared lens averages projected pixels, not independent K/D coefficients.
Camera positions here are ASSUMED, not a new extrinsic calibration.
"""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
LENS = ROOT.parent / "calibration/lens_20260908"
SIZE = np.array([1920, 1200])


def project_lens(rays, model):
    k = np.asarray(model["K"])
    d = np.asarray(model["D"])
    radius = np.linalg.norm(rays[:, :2], axis=1)
    theta = np.arctan2(radius, rays[:, 2])
    theta2 = theta * theta
    radial = theta * (1 + sum(d[i] * theta2 ** (i + 1) for i in range(4)))
    scale = np.divide(radial, radius, out=np.ones_like(radius), where=radius > 1e-12)
    return rays[:, :2] * scale[:, None] * [k[0, 0], k[1, 1]] + k[:2, 2]


def load_lenses():
    models = []
    sources = []
    for i in range(2):
        path = LENS / f"gmsl{i}_intrinsics.json"
        model = json.loads(path.read_text())
        if model["size"] != SIZE.tolist() or len(model["D"]) != 4:
            raise ValueError("Lens inputs must be matching 1920x1200 fisheye models")
        models.append(model)
        sources.append({"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "K": model["K"], "D": model["D"], "training_rms_px": model["training_rms_px"]})
    return models, sources


def camera_rays(world, slot, args):
    yaw = slot * np.pi / 2
    pitch = np.deg2rad(args.pitch)
    radial = np.array([np.sin(yaw), np.cos(yaw), 0.])
    center = radial * args.radius + [0, 0, args.height]
    forward = radial * np.cos(pitch) + [0, 0, -np.sin(pitch)]
    right = np.array([np.cos(yaw), -np.sin(yaw), 0.])
    down = np.cross(forward, right)
    return (world - center) @ np.stack([right, down, forward]).T


def map_view(uv, quadrant, models, args):
    world = np.c_[(uv[:, 0] - .5) * args.width,
                  (.5 - uv[:, 1]) * args.width * 720 / 1920,
                  np.zeros(len(uv))]
    slots = [quadrant, (quadrant + 3) % 4]
    sources, valid = [], []
    for slot in slots:
        rays = camera_rays(world, slot, args)
        pixels = np.mean([project_lens(rays, m) for m in models], axis=0)
        inside = (rays[:, 2] > 0) & np.isfinite(pixels).all(axis=1)
        inside &= (pixels >= 0).all(axis=1) & (pixels <= SIZE - 1).all(axis=1)
        # The earlier fitting PNGs were rotated 180 degrees from native UYVY.
        if args.rotate_180:
            pixels = SIZE - 1 - pixels
        sources.append(np.clip(pixels, 0, SIZE - 1) + .5)
        valid.append(inside)
    x, y = world[:, 0], world[:, 1]
    axis = [y, x, -y, -x]
    alpha = np.clip(.5 + (axis[slots[0]] - axis[slots[1]]) / args.feather, 0, 1)
    alpha = np.where(~valid[1], 1, alpha)
    alpha = np.where(~valid[0], 0, alpha)
    weights = np.c_[alpha, 1 - alpha]
    weights[~(valid[0] | valid[1])] = 0
    weights[np.linalg.norm(world[:, :2], axis=1) < args.hole] = 0
    return sources, weights


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "calibration")
    parser.add_argument("--height", type=float, default=760, help="ASSUMED camera height, mm")
    parser.add_argument("--radius", type=float, default=100, help="ASSUMED ring radius, mm")
    parser.add_argument("--pitch", type=float, default=55, help="ASSUMED downward angle, degrees")
    parser.add_argument("--width", type=float, default=2800, help="Ground view width, mm")
    parser.add_argument("--feather", type=float, default=100, help="Blend zone, mm")
    parser.add_argument("--hole", type=float, default=120, help="Hidden center radius, mm")
    parser.add_argument("--rotate-180", action=argparse.BooleanOptionalAction, default=True)
    args = parser.parse_args()
    if not (args.height > 0 and args.width > 0 and args.feather > 0 and
            0 < args.pitch < 90 and args.radius >= 0 and args.hole >= 0):
        parser.error("Invalid assumed camera geometry")
    models, sources = load_lenses()
    meshes, blends = [], []
    for q in range(4):
        col, row = np.meshgrid(np.linspace(0, 1, 136), np.linspace(0, 1, 136))
        uv = np.c_[col.ravel(), row.ravel()] * .5 + [0 if q in (0, 3) else .5, 0 if q < 2 else .5]
        pixels, weights = map_view(uv, q, models, args)
        entry = np.zeros((len(uv), 7), dtype="<i2")
        entry[:, 0] = np.rint(uv[:, 0] * 1080 - 540)
        entry[:, 1] = np.rint(540 - uv[:, 1] * 1080)
        for offset, source in zip((3, 5), pixels):
            entry[:, offset] = np.rint(source[:, 1] * 16)
            entry[:, offset + 1] = np.rint(source[:, 0] * 16)
        a = np.rint(weights[:, 0] * 255).astype(np.uint8)
        b = np.where(weights.sum(axis=1) > 0, 255 - a, 0).astype(np.uint8)
        meshes.append(entry)
        blends.append(np.c_[a, b])
    args.out.mkdir(parents=True, exist_ok=True)
    mesh = np.concatenate(meshes)
    blend = np.concatenate(blends)
    assert mesh.shape == (4 * 136 * 136, 7) and blend.shape == (4 * 136 * 136, 2)
    assert np.all((blend.sum(axis=1) == 0) | (blend.sum(axis=1) == 255))
    mesh.tofile(args.out / "four_mesh.bin")
    blend.tofile(args.out / "four_blend.bin")
    theta, phi = np.meshgrid(np.linspace(0, 1.05, 200), np.linspace(0, 2 * np.pi, 200))
    rays = np.c_[np.sin(theta.ravel()) * np.cos(phi.ravel()),
                 np.sin(theta.ravel()) * np.sin(phi.ravel()), np.cos(theta.ravel())]
    p0, p1 = [project_lens(rays, m) for m in models]
    inside = ((p0 >= 0) & (p0 <= SIZE - 1) & (p1 >= 0) & (p1 <= SIZE - 1)).all(axis=1)
    difference = np.linalg.norm(p0[inside] - p1[inside], axis=1)
    settings = {k: v for k, v in vars(args).items() if k != "out"}
    settings.update(status="APPROXIMATE DEMO: assumed poses, not calibrated seams",
                    lens_method="Equal-weight average of the two projected pixel coordinates for each 3D ray",
                    lens_sources=sources, capture_size=SIZE.tolist(), output_size=[1920, 720],
                    slot_order=["front", "right", "rear", "left"],
                    lens_difference_px={"median": float(np.median(difference)), "max": float(difference.max())},
                    valid_mesh_fraction=float(np.mean(blend.sum(axis=1) != 0)),
                    sha256={name: hashlib.sha256((args.out/name).read_bytes()).hexdigest()
                            for name in ("four_mesh.bin", "four_blend.bin")})
    (args.out / "settings.json").write_text(json.dumps(settings, indent=2) + "\n")
    print(json.dumps({k: settings[k] for k in ("status", "lens_difference_px", "valid_mesh_fraction")}, indent=2))


if __name__ == "__main__":
    main()
