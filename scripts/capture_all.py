"""Render two objects concurrently on CPU, without competing with GPU training."""
import argparse
import concurrent.futures
import subprocess
from pathlib import Path
from pipeline import PROJECT, manifest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--work', type=Path, default=PROJECT/'runs')
    p.add_argument('--workers', type=int, default=2)
    args = p.parse_args()
    def capture(obj):
        out = args.work/obj['uid']/'capture_512'
        if (out/'capture.json').exists():
            return obj['uid'], 0
        out.mkdir(parents=True, exist_ok=True)
        command = ['blender','-b','-P',str(PROJECT/'scripts/render_views.py'),'--',
                   '--glb',str(Path('/mnt/afs/260010017/data/objaverse/glbs')/obj['relative_glb']),
                   '--out',str(out.resolve())]
        with (out.parent/'capture.log').open('w') as log:
            proc = subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        print(obj['uid'],proc.returncode,flush=True)
        return obj['uid'],proc.returncode
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(capture, manifest(PROJECT/'configs/objects.json')))
    raise SystemExit(1 if any(code for _,code in results) else 0)


if __name__ == '__main__':
    main()
