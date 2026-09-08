#!/usr/bin/env python3
"""Fit a scene-specific floor warp; this does not replace intrinsic calibration."""
from pathlib import Path
import json
import cv2
import numpy as np
from scipy.optimize import least_squares

ROOT = Path(__file__).resolve().parent
CENTER = np.array([959.5, 599.5])
SQUARE_MM = 27.25


def undistort(points, focal):
    delta = points - CENTER
    radius = np.linalg.norm(delta, axis=-1)
    theta = 2 * np.arcsin(np.clip(radius / (2*focal), 0, .999))
    return CENTER + delta * (focal*np.tan(theta)/np.maximum(radius,1e-8))[...,None]


def homography(points, matrix):
    out = np.c_[points, np.ones(len(points))] @ matrix.T
    return out[:,:2] / out[:,2:]


def project(points, parameters):
    matrix = np.r_[parameters[:8], 1].reshape(3,3)
    focal = parameters[8]
    ideal = homography(points, matrix)
    delta = ideal - CENTER
    radius = np.linalg.norm(delta,axis=1)
    theta = np.arctan(radius / focal)
    return CENTER + delta*(2*focal*np.sin(theta/2)/np.maximum(radius,1e-8))[:,None]


def fit(camera):
    data = np.load(ROOT/f"grid{camera}.npz")
    points, grid = data['points'], data['grid'].astype(float)
    h, ok = cv2.findHomography(grid, undistort(points,1029), cv2.RANSAC, 12)
    initial = np.r_[h.ravel()[:8],1029]
    fitted = least_squares(lambda p:(project(grid,p)-points).ravel(),initial,
                           loss='soft_l1',f_scale=3,x_scale='jac',max_nfev=300,
                           bounds=(np.r_[np.full(8,-np.inf),850],np.r_[np.full(8,np.inf),1400]))
    errors = np.linalg.norm(project(grid,fitted.x)-points,axis=1)
    keep = errors < 12
    print(camera,'focal',fitted.x[8], 'points',len(grid), 'kept',keep.sum(),
          'error quantiles',np.percentile(errors,[50,75,90,99]),flush=True)
    return {'camera':camera,'parameters':fitted.x,'grid':grid[keep],'points':points[keep]}


def marker_grid(model):
    # Corresponding black marker corners, clockwise from its printed top left.
    seeds = ([[1584,366],[1669,432],[1653,489],[1561,418]] if model['camera']==0
             else [[188,434],[263,353],[294,400],[212,486]])
    gray=cv2.imread(str(ROOT/f"captures/gmsl{model['camera']}.png"),0)
    corners=cv2.cornerSubPix(gray,np.array(seeds,dtype=np.float32).reshape(-1,1,2),
                             (5,5),(-1,-1),(3,30,.01)).reshape(-1,2)
    matrix=np.r_[model['parameters'][:8],1].reshape(3,3)
    return homography(undistort(corners,model['parameters'][8]),np.linalg.inv(matrix))


def main():
    models=[fit(i) for i in (0,1)]
    markers=[marker_grid(model) for model in models]
    print('marker grid coordinates',markers,flush=True)
    options=[]
    for swap in (False,True):
        for sx in (-1,1):
            for sy in (-1,1):
                rotation=np.diag([sx,sy])
                if swap:rotation=rotation[:,::-1]
                shift=np.rint(np.mean(markers[0]-markers[1]@rotation.T,axis=0))
                error=np.linalg.norm(markers[0]-(markers[1]@rotation.T+shift),axis=1).mean()
                options.append((error,rotation,shift))
    error,rotation,shift=min(options,key=lambda x:x[0])
    print('grid1 to grid0',rotation.tolist(),shift.tolist(),'marker error cells',error,flush=True)
    for i,model in enumerate(models):
        model['global_grid']=(model['grid'] if i==0 else model['grid']@rotation.T+shift)
    np.savez(ROOT/'fit.npz',**{f'{k}{i}':v for i,m in enumerate(models) for k,v in m.items()})
    (ROOT/'fit.json').write_text(json.dumps({'square_mm':SQUARE_MM,'marker_error_cells':float(error),
       'grid1_rotation':rotation.tolist(),'grid1_shift':shift.tolist(),
       'models':[{k:np.asarray(v).tolist() for k,v in model.items() if k not in ('points','grid','global_grid')}
                 for model in models]},indent=2)+'\n')


if __name__=='__main__':main()
