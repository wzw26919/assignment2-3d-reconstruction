"""Create a reviewable local submission bundle only when ten actual GIFs exist."""
import argparse
import csv
import html
import json
import shutil
import zipfile
from pathlib import Path

from PIL import Image
from pipeline import PROJECT, manifest, read_json, save_json


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--work',type=Path,default=PROJECT/'runs')
    p.add_argument('--out',type=Path,default=PROJECT/'submission')
    p.add_argument('--pose-mode',choices=['known','colmap'],default='colmap')
    args = p.parse_args()
    objects = manifest(PROJECT/'configs/objects.json')
    suffix = 'baseline_known' if args.pose_mode == 'known' else 'baseline'
    records = []
    for obj in objects:
        source = args.work/obj['uid']/suffix
        result = read_json(source/'result.json')
        if result['status'] != 'complete':
            raise RuntimeError(f"Incomplete object: {obj['uid']}")
        with Image.open(source/'reconstruction.gif') as gif:
            if gif.n_frames < 2:
                raise RuntimeError('Static image passed as GIF')
        records.append((obj,source,result))
    if args.out.exists():
        raise FileExistsError(f'Refusing to overwrite {args.out}')
    args.out.mkdir(parents=True)
    for name in ('scripts','configs','tests','artifacts','docs','prompts','references'):
        shutil.copytree(PROJECT/name,args.out/name,ignore=shutil.ignore_patterns('__pycache__','*.tmp'))
    for name in ('README.md','requirements.txt','requirements-report.txt','.gitignore'):
        shutil.copy2(PROJECT/name,args.out/name)
    rows, cards = [], []
    for obj,source,result in records:
        target = args.out/'results'/obj['uid']
        target.mkdir(parents=True)
        for name in ('reconstruction.gif','reconstruction.mp4','metrics.json','result.json'):
            shutil.copy2(source/name,target/name)
        for name in ('matches','evaluation','logs'):
            shutil.copytree(source/name,target/name,ignore=shutil.ignore_patterns('tensorboard') if name=='logs' else None)
        sfm=source.parent/'sfm'
        if sfm.exists():
            # Portable correspondences are already present in target/matches. Keep
            # camera/point models and logs; large descriptor databases stay in AFS.
            shutil.copytree(sfm,target/'sfm',ignore=shutil.ignore_patterns('images','database.db','matches'))
        shutil.copy2(source/'processed/transforms.json',target/'transforms.json')
        shutil.copy2(source/'processed/split.json',target/'split.json')
        shutil.copy2(source.parent/'capture_512/capture.json',target/'capture.json')
        if (source/'camera_path.json').exists():
            shutil.copy2(source/'camera_path.json',target/'camera_path.json')
        # Keep the actual controlled experiment outputs, not just summary numbers.
        for experiment in source.parent.iterdir():
            if experiment==source or not (experiment/'result.json').exists(): continue
            experiment_result=read_json(experiment/'result.json')
            if experiment_result.get('status')!='complete' or experiment_result.get('pose_mode') not in ('known','colmap'): continue
            destination=args.out/'experiments'/obj['uid']/experiment.name
            destination.mkdir(parents=True)
            for name in ('result.json','metrics.json','reconstruction.gif','reconstruction.mp4'):
                shutil.copy2(experiment/name,destination/name)
            for name in ('evaluation','logs'):
                shutil.copytree(experiment/name,destination/name,ignore=shutil.ignore_patterns('tensorboard') if name=='logs' else None)
            if experiment_result['variant'] in ('baseline','fixed_resolution','short_training'):
                save_json(destination/'matches_reference.json',{'path':f'../../../results/{obj["uid"]}/matches',
                          'reason':'Identical source image set and resolution; verified correspondences are shared.'})
            else:
                shutil.copytree(experiment/'matches',destination/'matches')
            shutil.copy2(experiment/'processed/split.json',destination/'split.json')
        row = {'uid':obj['uid'],'name':obj['name'],'category':obj['category'],
               'pose_mode':args.pose_mode,**result['metrics']['results'],
               'foreground_psnr':read_json(source/'evaluation/foreground_metrics.json')['mean_foreground_psnr']}
        rows.append(row)
        cards.append(f'<article><h2>{html.escape(obj["name"])}</h2><p>{obj["uid"]}</p>'
                     f'<img src="results/{obj["uid"]}/reconstruction.gif" alt="3DGS reconstruction">'
                     f'<p>PSNR {row.get("psnr",0):.2f} dB; foreground PSNR {row["foreground_psnr"]:.2f} dB</p>'
                     f'<a href="results/{obj["uid"]}/matches/matches_00.png">Verified image matches</a></article>')
    with (args.out/'results.csv').open('w',newline='',encoding='utf-8') as handle:
        fields = list(dict.fromkeys(key for row in rows for key in row))
        writer = csv.DictWriter(handle,fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Ten Object 3D Reconstruction Results</title>'
    page += '<style>body{font:16px system-ui;max-width:1150px;margin:40px auto;padding:20px}main{display:grid;grid-template-columns:1fr 1fr;gap:24px}article{border:1px solid #ccc;padding:16px}img{width:100%}p{overflow-wrap:anywhere}</style>'
    page += f'<h1>Ten Object 3D Reconstruction Results</h1><p>Camera protocol: {args.pose_mode}. GIFs are rendered from trained 3D Gaussian Splatting models.</p><p><a href="assignment2_report.pdf">Pipeline documentation and experiment analysis</a></p><main>' + ''.join(cards) + '</main></html>'
    (args.out/'index.html').write_text(page,encoding='utf-8')
    save_json(args.out/'completion.json',{'objects':len(records),'pose_mode':args.pose_mode,
              'submission_status':'Prepared locally for user review; not submitted or published.'})
    archive = args.out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as handle:
        for path in args.out.rglob('*'):
            if path.is_file(): handle.write(path,path.relative_to(args.out.parent))
    print(archive)


if __name__ == '__main__':
    main()
