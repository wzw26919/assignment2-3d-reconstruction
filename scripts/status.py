"""Compact progress snapshot without dumping training logs or credentials."""
import json
from pathlib import Path
from pipeline import PROJECT, read_json

objects=read_json(PROJECT/'configs/objects.json')['objects']
rows=[]
for obj in objects:
    base=PROJECT/'runs'/obj['uid']
    sfm=read_json(base/'sfm/result.json') if (base/'sfm/result.json').exists() else {}
    train=read_json(base/'baseline_known/result.json') if (base/'baseline_known/result.json').exists() else {}
    rows.append({'uid':obj['uid'],'name':obj['name'],
                 'capture':(base/'capture_512/capture.json').exists(),
                 'sfm_registered':sfm.get('registered'),'sfm_pairs':sfm.get('matches',{}).get('verified_pairs'),
                 'known_3dgs':train.get('status')})
print(json.dumps(rows,ensure_ascii=False,indent=2))
