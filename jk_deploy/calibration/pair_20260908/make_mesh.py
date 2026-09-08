#!/usr/bin/env python3
"""Bake raw/stitched comparison meshes for the isolated TI SRV pair test."""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from scipy.interpolate import CloughTocher2DInterpolator

ROOT = Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--x',type=float,default=-6)
    parser.add_argument('--y',type=float,default=-28)
    parser.add_argument('--width',type=float,default=32)
    parser.add_argument('--layout',choices=['split','full'],default='split')
    args=parser.parse_args()
    fit=np.load(ROOT/'fit.npz')
    maps=[CloughTocher2DInterpolator(fit[f'global_grid{i}'],fit[f'points{i}']) for i in (0,1)]
    aspect=640/800 if args.layout=='split' else 1280/800
    height=args.width/aspect

    def corrected(uv):
        world=uv*np.array([args.width,height])+[args.x,args.y]
        sources=[f(world) for f in maps]
        valid=[np.isfinite(s).all(axis=1) for s in sources]
        # A short feather centered on the shared marker's grid column.
        alpha=np.clip(.5+(10.5-world[:,0])/1.5,0,1)
        alpha=np.where(~valid[1],1,alpha)
        alpha=np.where(~valid[0],0,alpha)
        weights=np.c_[alpha,1-alpha]
        weights[~(valid[0]|valid[1])]=0
        return [np.nan_to_num(s) for s in sources],weights

    mesh=[]
    blends=[]
    for quadrant in range(4):
        left=quadrant in (0,3)
        top=quadrant in (0,1)
        col,row=np.meshgrid(np.linspace(0,1,136),np.linspace(0,1,136))
        local=np.c_[col.ravel(),row.ravel()]
        screen=local*.5+[0 if left else .5,0 if top else .5]
        if args.layout=='split' and left:
            sources=[local*[1919,1199]]*2
            weights=np.tile([1,0] if top else [0,1],(len(local),1))
        else:
            uv=screen.copy()
            if args.layout=='split':uv[:,0]=(uv[:,0]-.5)*2
            sources,weights=corrected(uv)
        # Renderer slot 0 is GMSL1; slot 3 is GMSL0. Inputs are 640x400
        # full-FOV fits with 40 rows of padding inside 640x480 images.
        normalized=[s/3+[0,40] for s in sources]
        entry=np.zeros((len(local),7),dtype='<i2')
        entry[:,0]=np.rint(screen[:,0]*1080-540)
        entry[:,1]=np.rint(540-screen[:,1]*1080)
        for offset,source in ((3,normalized[1]),(5,normalized[0])):
            entry[:,offset]=np.rint(np.clip(source[:,1],0,479)*16)
            entry[:,offset+1]=np.rint(np.clip(source[:,0],0,639)*16)
        mesh.append(entry)
        blends.append(np.rint(weights[:,::-1]*255).astype(np.uint8))
    np.concatenate(mesh).tofile(ROOT/f'{args.layout}_mesh.bin')
    np.concatenate(blends).tofile(ROOT/f'{args.layout}_blend.bin')

    width=640 if args.layout=='split' else 1280
    xx,yy=np.meshgrid(np.linspace(0,1,width),np.linspace(0,1,800))
    sources,weights=corrected(np.c_[xx.ravel(),yy.ravel()])
    corrected_views=[]
    for camera,source in enumerate(sources):
        image=cv2.imread(str(ROOT/f'captures/gmsl{camera}.png'))
        warped=cv2.remap(image,source[:,0].reshape(800,width).astype('float32'),
                         source[:,1].reshape(800,width).astype('float32'),cv2.INTER_LINEAR)
        corrected_views.append(warped)
        cv2.imwrite(str(ROOT/f'corrected_gmsl{camera}.png'),warped)
    stitched=sum(view.astype(float)*weights[:,i].reshape(800,width,1)
                 for i,view in enumerate(corrected_views)).clip(0,255).astype('uint8')
    preview=stitched
    if args.layout=='split':
        raw=np.concatenate([cv2.resize(cv2.imread(str(ROOT/f'captures/gmsl{i}.png')),
                                      (640,400),interpolation=cv2.INTER_AREA) for i in (0,1)])
        preview=np.concatenate([raw,stitched],axis=1)
    cv2.imwrite(str(ROOT/f'{args.layout}_preview.png'),preview)
    uncovered=float(np.mean(weights.sum(axis=1)==0))
    settings=vars(args)|{'height':height,'square_mm':27.25,'uncovered_fraction':uncovered,
                        'description':'Scene-specific checkerboard warp; not a full intrinsic calibration'}
    (ROOT/f'{args.layout}_settings.json').write_text(json.dumps(settings,indent=2)+'\n')
    print(settings,flush=True)


if __name__=='__main__':main()
