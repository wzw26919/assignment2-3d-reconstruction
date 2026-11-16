"""Wait for baseline completion, then run the frozen controlled comparisons."""
import subprocess
import sys
import time
from pipeline import PROJECT, manifest, read_json

objects=manifest(PROJECT/'configs/objects.json')
while True:
    states=[]
    for obj in objects:
        file=PROJECT/'runs'/obj['uid']/'baseline_known/result.json'
        states.append(read_json(file).get('status') if file.exists() else None)
    if all(state=='complete' for state in states): break
    if any(state=='failed' for state in states): raise RuntimeError('Inspect failed baseline before starting ablations')
    time.sleep(5)
protocol=read_json(PROJECT/'configs/ablations.json')
for variant in [protocol['reference_variant'],*protocol['variants']]:
    print('START',variant,flush=True)
    command=[sys.executable,str(PROJECT/'scripts/run_batch.py'),'--jobs','3','--variant',variant,
             '--pose-mode','known','--only',*protocol['uids']]
    process=subprocess.run(command)
    if process.returncode: raise RuntimeError(f'Ablation failed: {variant}')
print('ALL CONTROLLED COMPARISONS COMPLETE',flush=True)
