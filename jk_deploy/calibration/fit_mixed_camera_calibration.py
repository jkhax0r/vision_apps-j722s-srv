#!/usr/bin/env python3
"""Fit TI SRV camera matrices for a mixed equisolid camera set."""

import argparse
import json
import math
import struct
from pathlib import Path

import cv2
import numpy as np


ROTATION_SCALE = 1 << 30
TRANSLATION_SCALE = 1 << 10


def undistort_equisolid(points, focal, center):
    delta = points - center
    radius_distorted = np.linalg.norm(delta, axis=1)
    theta = 2.0 * np.arcsin(
        np.clip(radius_distorted / (2.0 * focal), -0.999999, 0.999999)
    )
    radius_undistorted = focal * np.tan(theta)
    scale = radius_undistorted / np.maximum(radius_distorted, 1.0e-12)
    return center + delta * scale[:, None]


def project_equisolid(parameters, world_points, focal, center):
    rotation, _ = cv2.Rodrigues(parameters[:3])
    camera_points = (rotation @ world_points.T).T + parameters[3:6]
    radial = np.linalg.norm(camera_points[:, :2], axis=1)
    theta = np.arctan2(radial, np.abs(camera_points[:, 2]))
    radius_distorted = 2.0 * focal * np.sin(theta * 0.5)
    scale = radius_distorted / np.maximum(radial, 1.0e-12)
    return center + camera_points[:, :2] * scale[:, None]


def refine_pose(parameters, world_points, image_points, focal, center):
    damping = 1.0e-3
    residual = (
        project_equisolid(parameters, world_points, focal, center) - image_points
    ).reshape(-1)
    cost = float(residual @ residual)

    for _ in range(200):
        jacobian = np.empty((residual.size, 6), dtype=np.float64)
        for column in range(6):
            epsilon = 1.0e-6 if column < 3 else 1.0e-3
            plus = parameters.copy()
            minus = parameters.copy()
            plus[column] += epsilon
            minus[column] -= epsilon
            jacobian[:, column] = (
                (
                    project_equisolid(plus, world_points, focal, center)
                    - project_equisolid(minus, world_points, focal, center)
                )
                / (2.0 * epsilon)
            ).reshape(-1)

        normal = jacobian.T @ jacobian
        gradient = jacobian.T @ residual
        diagonal = np.diag(np.diag(normal) + 1.0e-9)
        try:
            update = np.linalg.solve(normal + damping * diagonal, -gradient)
        except np.linalg.LinAlgError:
            damping *= 10.0
            continue

        candidate = parameters + update
        candidate_residual = (
            project_equisolid(candidate, world_points, focal, center) - image_points
        ).reshape(-1)
        candidate_cost = float(candidate_residual @ candidate_residual)
        if candidate_cost < cost:
            parameters = candidate
            residual = candidate_residual
            cost = candidate_cost
            damping = max(damping / 3.0, 1.0e-12)
            if np.linalg.norm(update) < 1.0e-10:
                break
        else:
            damping = min(damping * 10.0, 1.0e12)

    return parameters, math.sqrt(float(np.mean(residual * residual)))


def fit_camera(camera, center):
    focal = float(camera["focal"])
    image_points = np.asarray(camera["image_points"], dtype=np.float64)
    world_points = np.asarray(camera["world_points"], dtype=np.float64)
    undistorted = undistort_equisolid(image_points, focal, center)
    intrinsic = np.array(
        [[focal, 0.0, center[0]], [0.0, focal, center[1]], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    success, rotation_vector, translation = cv2.solvePnP(
        world_points, undistorted, intrinsic, None, flags=cv2.SOLVEPNP_ITERATIVE
    )
    if not success:
        raise RuntimeError(f"pose solve failed for {camera['name']}")

    parameters = np.concatenate((rotation_vector.reshape(3), translation.reshape(3)))
    parameters, rms = refine_pose(
        parameters, world_points, image_points, focal, center
    )
    rotation, _ = cv2.Rodrigues(parameters[:3])
    camera_center = -(rotation.T @ parameters[3:6])
    packed = np.concatenate((rotation.flatten(order="F"), parameters[3:6]))
    return packed, camera_center, rms


def encode_calmat(matrices, template):
    if template is not None:
        header = bytearray(template.read_bytes()[:128])
        if len(header) != 128:
            raise ValueError(f"{template} has a truncated CALMAT header")
    else:
        header = bytearray(128)
        struct.pack_into("<5i", header, 0, 4, 48, 48, 48, 48)

    encoded = bytearray(header)
    for matrix in matrices:
        fixed = []
        for index, value in enumerate(matrix):
            scale = ROTATION_SCALE if index < 9 else TRANSLATION_SCALE
            fixed.append(int(round(float(value) * scale)))
        encoded.extend(struct.pack("<12i", *fixed))
    return encoded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("points", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--template", type=Path)
    args = parser.parse_args()

    data = json.loads(args.points.read_text(encoding="utf-8"))
    center = np.asarray(data["principal_point"], dtype=np.float64)
    cameras = sorted(data["cameras"], key=lambda item: item["id"])
    if [camera["id"] for camera in cameras] != [0, 1, 2, 3]:
        raise ValueError("camera IDs must be exactly 0, 1, 2, 3")

    matrices = []
    centers = []
    for camera in cameras:
        matrix, camera_center, rms = fit_camera(camera, center)
        matrices.append(matrix)
        centers.append(camera_center)
        print(
            f"camera{camera['id']} {camera['name']}: focal={camera['focal']:.1f} "
            f"RMS={rms:.3f}px center=({camera_center[0]:.1f}, "
            f"{camera_center[1]:.1f}, {camera_center[2]:.1f})mm"
        )

    baseline = float(np.linalg.norm(centers[0][:2] - centers[2][:2]))
    print(f"front/back baseline={baseline:.1f}mm; TI auto scale={baseline / 100.0:.3f}mm/pixel")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(encode_calmat(matrices, args.template))
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
