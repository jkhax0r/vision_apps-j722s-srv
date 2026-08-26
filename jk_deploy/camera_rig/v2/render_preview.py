#!/usr/bin/env python3
"""Render binary STL assembly previews without an X11/OpenGL dependency."""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import PolyCollection


def read_binary_stl(path: Path) -> tuple[np.ndarray, np.ndarray]:
    data = path.read_bytes()
    if len(data) < 84:
        raise ValueError(f"{path} is too short to be a binary STL")
    triangle_count = struct.unpack_from("<I", data, 80)[0]
    expected_size = 84 + (triangle_count * 50)
    if len(data) != expected_size:
        raise ValueError(f"{path} is not the expected binary STL format")

    triangles = np.empty((triangle_count, 3, 3), dtype=np.float64)
    normals = np.empty((triangle_count, 3), dtype=np.float64)
    offset = 84
    for index in range(triangle_count):
        values = struct.unpack_from("<12fH", data, offset)
        normals[index] = values[0:3]
        triangles[index] = np.asarray(values[3:12]).reshape(3, 3)
        offset += 50
    return triangles, normals


def camera_basis(
    position: np.ndarray, target: np.ndarray, nominal_up: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    forward = target - position
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, nominal_up)
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    return right, up, forward


def project(
    triangles: np.ndarray,
    position: np.ndarray,
    right: np.ndarray,
    up: np.ndarray,
    forward: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    relative = triangles - position
    camera_x = np.einsum("tvc,c->tv", relative, right)
    camera_y = np.einsum("tvc,c->tv", relative, up)
    camera_z = np.einsum("tvc,c->tv", relative, forward)
    if np.any(camera_z <= 0.0):
        raise ValueError("Preview camera intersects or points away from the model")
    projected = np.stack((camera_x / camera_z, camera_y / camera_z), axis=2)
    return projected, camera_z.mean(axis=1)


def shaded_colors(
    normals: np.ndarray, base_color: tuple[float, float, float]
) -> np.ndarray:
    light = np.asarray((0.35, -0.45, 0.82), dtype=np.float64)
    light /= np.linalg.norm(light)
    lengths = np.linalg.norm(normals, axis=1)
    safe_normals = normals / np.maximum(lengths[:, None], 1.0e-9)
    diffuse = np.abs(safe_normals @ light)
    intensity = 0.42 + (0.58 * diffuse)
    colors = intensity[:, None] * np.asarray(base_color)[None, :]
    alpha = np.ones((len(colors), 1), dtype=np.float64)
    return np.concatenate((np.clip(colors, 0.0, 1.0), alpha), axis=1)


def render(input_dir: Path, output_path: Path) -> None:
    meshes = (
        (
            input_dir / "camera_rig_printed_assembly_preview.stl",
            (0.16, 0.48, 0.82),
        ),
        (
            input_dir / "camera_rig_camera_references_preview.stl",
            (0.22, 0.23, 0.25),
        ),
        (
            input_dir / "camera_rig_hardware_references_preview.stl",
            (0.70, 0.72, 0.75),
        ),
    )

    position = np.asarray((245.0, -245.0, 205.0))
    target = np.asarray((0.0, 0.0, 20.0))
    right, up, forward = camera_basis(position, target, np.asarray((0.0, 0.0, 1.0)))

    all_polygons = []
    all_depths = []
    all_colors = []
    for path, base_color in meshes:
        triangles, normals = read_binary_stl(path)
        polygons, depths = project(triangles, position, right, up, forward)
        all_polygons.append(polygons)
        all_depths.append(depths)
        all_colors.append(shaded_colors(normals, base_color))

    polygons = np.concatenate(all_polygons, axis=0)
    depths = np.concatenate(all_depths, axis=0)
    colors = np.concatenate(all_colors, axis=0)
    order = np.argsort(depths)[::-1]

    fig, axis = plt.subplots(figsize=(14.0, 10.5), dpi=100)
    fig.patch.set_facecolor((0.94, 0.95, 0.96))
    axis.set_facecolor((0.94, 0.95, 0.96))
    collection = PolyCollection(
        polygons[order],
        facecolors=colors[order],
        edgecolors=(0.03, 0.04, 0.05, 0.06),
        linewidths=0.08,
        antialiased=True,
    )
    axis.add_collection(collection)
    axis.autoscale_view()
    axis.set_aspect("equal", adjustable="box")
    axis.margins(0.08)
    axis.axis("off")
    fig.subplots_adjust(left=0.0, right=1.0, bottom=0.0, top=1.0)
    fig.savefig(output_path, facecolor=fig.get_facecolor(), dpi=100)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "camera_rig_preview.png",
    )
    args = parser.parse_args()
    render(args.input_dir, args.output)


if __name__ == "__main__":
    main()
