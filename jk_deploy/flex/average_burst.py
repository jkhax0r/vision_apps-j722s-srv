#!/usr/bin/env python3
"""Average every captured frame; motion checks are advisory diagnostics only."""
import hashlib
from pathlib import Path

import cv2
import numpy as np

FRAME_BYTES = 1920*1200*2
DEFAULT_LIMITS = {"median_motion_px": .75, "p95_motion_px": 2., "changed_tile_fraction": .06}


def motion_gray(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (960, 600), interpolation=cv2.INTER_AREA)
    return cv2.createCLAHE(clipLimit=2., tileGridSize=(12, 10)).apply(gray)


def texture_changes(a, b):
    # Local correlation tolerates exposure changes without registering/moving pixels.
    def tiles(image):
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (960, 600), interpolation=cv2.INTER_AREA).astype(float)
        values = small.reshape(25, 24, 30, 32).transpose(0, 2, 1, 3).reshape(-1, 24*32)
        return values-values.mean(1, keepdims=True)
    x, y = tiles(a), tiles(b)
    valid = (x.std(1) > 8) & (y.std(1) > 8)
    if valid.sum() < 100:
        raise ValueError("Too little stable texture for a motion check")
    correlation = np.sum(x[valid]*y[valid], axis=1)/np.sqrt(np.sum(x[valid]**2, axis=1)*np.sum(y[valid]**2, axis=1))
    return float(np.mean(correlation < .90))


def check_stationary(reference, frame, limits=None):
    limits = limits or DEFAULT_LIMITS
    a, b = motion_gray(reference), motion_gray(frame)
    corners = cv2.goodFeaturesToTrack(a, 1500, .03, 10, blockSize=5)
    if corners is None or len(corners) < 100:
        raise ValueError("Not enough image features to check motion")
    params = dict(winSize=(21, 21), maxLevel=3,
                  criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 30, .01))
    tracked, ok, _ = cv2.calcOpticalFlowPyrLK(a, b, corners, None, **params)
    back, ok_back, _ = cv2.calcOpticalFlowPyrLK(b, a, tracked, None, **params)
    valid = ok.ravel().astype(bool) & ok_back.ravel().astype(bool)
    valid &= np.linalg.norm(back-corners, axis=2).ravel() < .5
    if valid.sum() < 100 or valid.mean() < .75:
        raise ValueError("Too many features moved, disappeared, or became unreliable")
    distances = 2*np.linalg.norm(tracked-corners, axis=2).ravel()[valid]
    result = {"median_motion_px": float(np.median(distances)),
              "p95_motion_px": float(np.percentile(distances, 95)),
              "tracked_features": int(valid.sum()), "tracked_fraction": float(valid.mean()),
              "changed_tile_fraction": texture_changes(reference, frame)}
    for key, maximum in limits.items():
        if result[key] > maximum:
            raise ValueError(f"Motion/occlusion check failed: {key}={result[key]:.3f} > {maximum}; keep rig and scene still")
    return result


def motion_diagnostic(reference, frame):
    try:
        return dict(passed=True, **check_stationary(reference, frame))
    except (ValueError, cv2.error) as error:
        return {"passed": False, "warning": str(error)}


def average_frames(frames):
    count = len(frames)
    if not 6 <= count <= 32:
        raise ValueError("Need 6..32 frames per burst")
    reference = frames[0]
    if reference.shape != (1200, 1920, 3) or reference.dtype != np.uint8:
        raise ValueError("Need native 1920x1200 uint8 BGR frames")
    total = np.zeros(reference.shape, np.uint32)
    observations, luma, signatures = [], [], set()
    for i, frame in enumerate(frames):
        if frame.shape != reference.shape or frame.dtype != np.uint8:
            raise ValueError("Burst frame dimensions/types changed")
        signatures.add(hashlib.sha256(frame.tobytes()).hexdigest())
        if i:
            observations.append(dict(frame=i, **motion_diagnostic(reference, frame)))
        total += frame
        luma.append(float(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY).mean()))
    if len(signatures) < 3:
        raise ValueError("Fewer than three distinct frames; capture may be stalled or duplicated")
    averaged = ((total+count//2)//count).astype(np.uint8)
    return averaged, {"frames": count, "distinct_frames": len(signatures), "frame_mean_luma": luma,
                      "mean_luma_peak_to_peak": max(luma)-min(luma), "motion": observations,
                      "motion_limits": DEFAULT_LIMITS, "motion_policy": "warn_only",
                      "method": "Arithmetic mean of unregistered BGR frames"}


def average_raw(path, count):
    path = Path(path)
    if not 6 <= count <= 32 or path.stat().st_size != count*FRAME_BYTES:
        raise ValueError(f"Wrong raw burst length: {path}")
    raw = np.memmap(path, dtype=np.uint8, mode="r", shape=(count, 1200, 1920, 2))
    # At most 32 converted frames (~211 MiB); raw data stays memory mapped.
    frames = [cv2.cvtColor(frame, cv2.COLOR_YUV2BGR_UYVY) for frame in raw]
    return average_frames(frames)
