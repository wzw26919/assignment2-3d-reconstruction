"""Run real COLMAP SfM independently of training and compare to capture calibration."""
import argparse
import json
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
from export_matches import export
from pipeline import PROJECT, manifest, read_json, save_json


def read_poses(path):
    lines = path.read_text().splitlines()
    poses = {}; i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith('#'):
            i += 1; continue
        values = line.split()
        qw,qx,qy,qz,tx,ty,tz = map(float, values[1:8])
        rotation = np.array([[1-2*qy*qy-2*qz*qz,2*qx*qy-2*qz*qw,2*qx*qz+2*qy*qw],
                             [2*qx*qy+2*qz*qw,1-2*qx*qx-2*qz*qz,2*qy*qz-2*qx*qw],
                             [2*qx*qz-2*qy*qw,2*qy*qz+2*qx*qw,1-2*qx*qx-2*qy*qy]])
        center = -rotation.T @ np.array([tx,ty,tz])
        poses[values[9]] = (center, rotation.T @ np.diag([1,-1,-1]))
        i += 2  # The next line is the feature/track list, which can be empty.
    return poses


def compare_poses(estimated, frames):
    known = {f['file_path']:np.array(f['transform_matrix']) for f in frames}
    names = sorted(set(estimated)&set(known))
    if len(names)<3:
        return {'matched_cameras':len(names)}
    source = np.array([estimated[n][0] for n in names])
    target = np.array([known[n][:3,3] for n in names])
    a,b = source-source.mean(0), target-target.mean(0)
    u,s,vh = np.linalg.svd(b.T@a/len(names))
    sign = np.diag([1,1,np.linalg.det(u@vh)])
    rotation = u@sign@vh
    scale = np.trace(np.diag(s)@sign)/np.mean(np.sum(a*a,axis=1))
    translation = target.mean(0)-scale*rotation@source.mean(0)
    aligned = scale*(source@rotation.T)+translation
    errors = np.linalg.norm(aligned-target,axis=1)
    angles = []
    for name in names:
        delta = known[name][:3,:3].T @ rotation @ estimated[name][1]
        angles.append(float(np.degrees(np.arccos(np.clip((np.trace(delta)-1)/2,-1,1)))))
    return {'matched_cameras':len(names),'center_rmse':float(np.sqrt(np.mean(errors**2))),
            'center_median':float(np.median(errors)), 'rotation_median_degrees':float(np.median(angles)),
            'alignment_scale':float(scale),'alignment_rotation':rotation.tolist(),
            'alignment_translation':translation.tolist(),
            'units':'Capture coordinates: source mesh longest side is 2 units.'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--work',type=Path,default=PROJECT/'runs')
    p.add_argument('--only',nargs='*')
    args=p.parse_args()
    objects=manifest(PROJECT/'configs/objects.json')
    for obj in objects:
        uid=obj['uid']
        if args.only and uid not in args.only: continue
        base=args.work/uid; capture=base/'capture_512'; work=base/'sfm'
        if (work/'result.json').exists(): continue
        if not (capture/'capture.json').exists():
            print('WAIT capture',uid,flush=True); continue
        meta=read_json(capture/'capture.json')
        if meta.get('capture_version')!=2: raise ValueError('Unexpected capture version')
        work.mkdir(exist_ok=True); images=work/'images'; images.mkdir(exist_ok=True)
        for frame in meta['frames']:
            shutil.copy2(capture/frame['file_path'],images/frame['file_path'])
        db=work/'database.db'; journal=[]
        def call(command, log):
            start=time.monotonic()
            with (work/log).open('w') as handle:
                done=subprocess.run(list(map(str,command)),stdout=handle,stderr=subprocess.STDOUT,timeout=900)
            journal.append({'command':list(map(str,command)),'returncode':done.returncode,'seconds':time.monotonic()-start})
            if done.returncode: raise RuntimeError(log)
        result={'uid':uid,'commands':journal}
        try:
            call(['colmap','feature_extractor','--database_path',db,'--image_path',images,
                  '--ImageReader.single_camera','1','--ImageReader.camera_model','PINHOLE',
                  '--SiftExtraction.use_gpu','0','--SiftExtraction.num_threads','6'],'features.log')
            call(['colmap','exhaustive_matcher','--database_path',db,'--SiftMatching.use_gpu','0',
                  '--SiftMatching.num_threads','6'],'matching.log')
            result['matches']=export(db,images,work/'matches')
            sparse=work/'sparse'; sparse.mkdir(exist_ok=True)
            call(['colmap','mapper','--database_path',db,'--image_path',images,
                  '--output_path',sparse,'--Mapper.num_threads','6'],'mapper.log')
            models=[]
            for model in sorted(sparse.iterdir()):
                if not (model/'images.bin').exists(): continue
                text=work/('model_text_'+model.name); text.mkdir(exist_ok=True)
                call(['colmap','model_converter','--input_path',model,'--output_path',text,
                      '--output_type','TXT'],f'convert_{model.name}.log')
                poses=read_poses(text/'images.txt')
                models.append((len(poses),model,poses))
            if not models: raise RuntimeError('No reconstructed COLMAP model')
            count,model,poses=max(models,key=lambda x:x[0])
            result.update(status='complete',registered=count,input_images=len(meta['frames']),
                          registration_ratio=count/len(meta['frames']),model_path=str(model.resolve()),
                          camera_error=compare_poses(poses,meta['frames']))
        except Exception as error:
            result.update(status='failed',error=str(error))
        save_json(work/'result.json',result)
        print(json.dumps(result),flush=True)


if __name__=='__main__': main()
