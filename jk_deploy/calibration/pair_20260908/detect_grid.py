#!/usr/bin/env python3
"""Grow the September 8 cloth grid from four inspected corners per camera."""
from pathlib import Path
import cv2
import numpy as np
from scipy.spatial import cKDTree

root = Path(__file__).resolve().parent
cv2.setNumThreads(4)
for camera in (0, 1):
    image = cv2.imread(str(root / f"captures/gmsl{camera}.png"))
    if image is None or image.shape[:2] != (1200, 1920):
        raise ValueError(f"Expected captures/gmsl{camera}.png at 1920x1200, rotated 180 degrees")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # These four inspected corners bound one physical 27.25 mm cell.
    seeds = (
        [[982,483],[1022,511],[946,512],[988,543]],
        [[979,509],[1025,540],[941,548],[987,582]],
    )[camera]
    image_points = cv2.cornerSubPix(gray,np.array(seeds,dtype=np.float32).reshape(-1,1,2),
                                   (4,4),(-1,-1),(3,30,0.01)).reshape(-1,2)
    grid_points = np.array([[0,0],[1,0],[0,1],[1,1]])
    candidates = cv2.goodFeaturesToTrack(gray, 10000, 0.035, 7, blockSize=5)
    candidates = cv2.cornerSubPix(gray, candidates, (4,4), (-1,-1),
                                 (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT,30,0.01)).reshape(-1,2)
    masks = ([[1530,320,1715,525],[1430,365,1540,475]] if camera == 0
             else [[150,315,315,510],[135,510,235,635]])
    for x0,y0,x1,y1 in masks:
        candidates = candidates[~((candidates[:,0]>=x0)&(candidates[:,0]<=x1)&
                                  (candidates[:,1]>=y0)&(candidates[:,1]<=y1))]
    tree = cKDTree(candidates)
    grid = {tuple(uv): point for uv,point in zip(grid_points,image_points)}
    for iteration in range(100):
        proposals = {}
        for uv, point in list(grid.items()):
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                next_uv = (uv[0]+dx,uv[1]+dy)
                prev_uv = (uv[0]-dx,uv[1]-dy)
                if next_uv in grid or prev_uv not in grid:
                    continue
                step = point-grid[prev_uv]
                distance, idx = tree.query(point+step)
                if distance < min(9,0.24*np.linalg.norm(step)):
                    proposals.setdefault(next_uv,[]).append(candidates[idx])
        used = cKDTree(np.array(list(grid.values())))
        count = 0
        for uv, points in proposals.items():
            point = np.mean(points,axis=0)
            if max(np.linalg.norm(np.array(points)-point,axis=1)) > 2:
                continue
            if used.query(point)[0] < 5:
                continue
            grid[uv] = point
            count += 1
        if not count:
            break
    grid_points = np.array(list(grid))
    image_points = np.array(list(grid.values()))
    np.savez(root / f"grid{camera}.npz", points=image_points, grid=grid_points)
    print(camera, len(image_points), 'range',grid_points.min(0),grid_points.max(0),flush=True)
    for point, uv in zip(image_points, grid_points):
        point = tuple(np.rint(point).astype(int))
        cv2.circle(image, point, 3, (0, 0, 255), -1)
        if uv[0] % 2 == 0 and uv[1] % 2 == 0:
            cv2.putText(image, f"{uv[0]},{uv[1]}", point, cv2.FONT_HERSHEY_SIMPLEX,
                        0.35, (0, 255, 0), 1)
    cv2.imwrite(str(root / f"grid{camera}.png"), image)
