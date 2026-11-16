"""Run independent object jobs with bounded GPU concurrency, retaining each log."""
import argparse
import concurrent.futures
import subprocess
import sys
from pipeline import PROJECT, manifest


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--jobs',type=int,default=3)
    p.add_argument('--variant',default='baseline')
    p.add_argument('--pose-mode',choices=['known','colmap'],default='known')
    p.add_argument('--only',nargs='*')
    p.add_argument('--exclude',nargs='*',default=[])
    args=p.parse_args()
    objects=manifest(PROJECT/'configs/objects.json')
    uids=[o['uid'] for o in objects if o['uid'] not in args.exclude and (not args.only or o['uid'] in args.only)]
    def execute(uid):
        log=PROJECT/'artifacts'/f'batch_{args.variant}_{args.pose_mode}_{uid}.log'
        command=[sys.executable,str(PROJECT/'scripts/pipeline.py'),'--pose-mode',args.pose_mode,
                 '--variant',args.variant,'--only',uid,'--resume']
        with log.open('w') as handle:
            result=subprocess.run(command,stdout=handle,stderr=subprocess.STDOUT)
        print(uid,result.returncode,flush=True)
        return result.returncode
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        codes=list(pool.map(execute,uids))
    raise SystemExit(1 if any(codes) else 0)


if __name__=='__main__':main()
