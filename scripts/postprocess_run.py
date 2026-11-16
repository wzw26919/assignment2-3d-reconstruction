"""Recover evaluation/rendering after an inspected fix without retraining."""
import argparse
import traceback
from pathlib import Path
from pipeline import read_json, save_json, postprocess

p=argparse.ArgumentParser()
p.add_argument('--run',type=Path,required=True)
args=p.parse_args()
work=args.run.resolve();result=read_json(work/'result.json')
if not any(c['command'][0]=='ns-train' and c.get('returncode')==0 for c in result['commands']):
    raise RuntimeError('No successfully trained checkpoint; this command cannot replace training')
result.setdefault('recovery_history',[]).append({'status':result['status'],'error':result.get('error')})
result.pop('error',None);result.pop('traceback',None)
try:
    postprocess(work,work.parent/'capture_512',result['pose_mode'],result)
except Exception as error:
    result.update(status='failed',error=str(error),traceback=traceback.format_exc())
    raise
finally:
    save_json(work/'result.json',result)
