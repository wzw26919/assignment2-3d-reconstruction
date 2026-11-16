"""Sequential, logged pipeline. Source GLBs remain read-only. No implicit submission."""
import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

from probe_afs import check_glb, probe, ROOTS
from export_matches import export

PROJECT = Path(__file__).resolve().parents[1]
VARIANTS = {
    'baseline': {'stride': 1, 'size': 512, 'steps': 15000, 'downscales':2},
    'fixed_resolution': {'stride': 1, 'size': 512, 'steps': 15000, 'downscales':0},
    'few_views': {'stride': 2, 'size': 512, 'steps': 15000, 'downscales':0},
    'low_resolution': {'stride': 1, 'size': 256, 'steps': 15000, 'downscales':0},
    'short_training': {'stride': 1, 'size': 512, 'steps': 3000, 'downscales':0},
}


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    tmp.replace(path)


def manifest(path, count=10):
    value = read_json(path)
    if not value.get('assignment1_manifest'):
        raise ValueError('Record the Assignment 1 cleaned manifest path in assignment1_manifest first')
    objects = value['objects']
    if len(objects) != count:
        raise ValueError(f'Exactly {count} objects required; found {len(objects)}')
    uids = [o['uid'] for o in objects]
    if len(set(uids)) != len(uids):
        raise ValueError('Duplicate object UID')
    for obj in objects:
        if not obj['uid'] or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in obj['uid']):
            raise ValueError('UID must be a safe directory name')
        path = Path(obj['relative_glb'])
        if path.is_absolute() or '..' in path.parts or path.suffix.lower() != '.glb':
            raise ValueError('relative_glb must be a GLB path relative to the glbs directory')
        if not obj.get('selection_reason'):
            raise ValueError('Record selection_reason for every object')
    return objects


def run(command, log, journal):
    command = [str(x) for x in command]
    start = time.monotonic()
    entry = {'command': command, 'started_utc': datetime.now(timezone.utc).isoformat()}
    journal.append(entry)
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.exists():
        archived=log.with_name(log.stem+'_previous_'+uuid.uuid4().hex[:8]+log.suffix)
        log.rename(archived)
        for old in journal[:-1]:
            if old.get('log')==str(log): old['log']=str(archived)
    print('RUN', command, flush=True)
    with log.open('w', encoding='utf-8') as handle:
        proc = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, cwd=PROJECT)
    entry.update(returncode=proc.returncode, seconds=time.monotonic()-start, log=str(log))
    if proc.returncode:
        raise RuntimeError(f'Command failed ({proc.returncode}): see {log}')


def select_images(source, target, stride, size):
    from PIL import Image
    target.mkdir(parents=True, exist_ok=False)
    captures = read_json(source / 'capture.json')
    chosen = [f for f in captures['frames'] if f['azimuth'] % stride == 0]
    for frame in chosen:
        name = frame['file_path']
        with Image.open(source / name) as image:
            image.resize((size, size), Image.Resampling.LANCZOS).save(target / name)
    return chosen


def verify_sfm(processed, expected):
    transforms = read_json(processed / 'transforms.json')
    count = len(transforms['frames'])
    if count < 12 or count / expected < 0.8:
        raise RuntimeError(f'SfM registered {count}/{expected}; inspect failure before training')
    if not (processed / 'sparse_pc.ply').exists():
        raise RuntimeError('COLMAP sparse point cloud missing; refuse silent random initialization')
    return {'registered': count, 'input_images': expected, 'registration_ratio': count / expected}


def set_split(processed):
    transforms = read_json(processed / 'transforms.json')
    frames = sorted(transforms['frames'], key=lambda x: x['file_path'])
    if len(frames) < 12:
        raise RuntimeError('Too few registered frames')
    # Fix the split explicitly, never permit ns-eval to fall back to training views.
    original_names = all(Path(f['file_path']).stem.startswith('r') and '_' in Path(f['file_path']).stem for f in frames)
    evaluation = [f['file_path'] for i, f in enumerate(frames)
                  if (int(Path(f['file_path']).stem.split('_')[1]) % 6 == 0 if original_names else i % 8 == 0)]
    training = [f['file_path'] for f in frames if f['file_path'] not in evaluation]
    for split, files in [('train', training), ('val', evaluation), ('test', evaluation)]:
        transforms[f'{split}_filenames'] = files
    save_json(processed / 'transforms.json', transforms)
    save_json(processed / 'split.json', {'training': training, 'evaluation': evaluation,
              'protocol': 'Evaluation RGB loss withheld; all images participate in transductive COLMAP geometry and colored-point initialization.'})
    return len(training), len(evaluation)


def known_pose_dataset(capture, chosen, processed, size):
    """Image-only 3DGS with synthetic camera calibration; no source mesh points."""
    meta = read_json(capture/'capture.json')
    frames = []
    for frame in chosen:
        frames.append({'file_path': 'images/'+frame['file_path'],
                       'transform_matrix': frame['transform_matrix'],
                       'azimuth': frame['azimuth'], 'ring': frame['ring']})
    ratio = size/meta['w']
    transforms = {k: meta[k]*ratio for k in ('fl_x', 'fl_y', 'cx', 'cy')}
    transforms.update(w=size, h=size, camera_model='OPENCV', frames=frames)
    # Shared evaluation azimuths are included in both full and sparse-view variants.
    evaluation = [f['file_path'] for f in frames if f['azimuth'] % 6 == 0]
    training = [f['file_path'] for f in frames if f['file_path'] not in evaluation]
    transforms.update(train_filenames=training, val_filenames=evaluation, test_filenames=evaluation)
    save_json(processed/'transforms.json', transforms)
    save_json(processed/'split.json', {'training': training, 'evaluation': evaluation,
              'protocol': 'Known synthetic camera poses; evaluation RGB excluded from optimization and initialization.'})
    return len(training), len(evaluation)


def gif_from_video(video, target, logs, journal):
    palette = target.with_suffix('.palette.png')
    filters = 'fps=15,scale=480:-1:flags=lanczos'
    run(['ffmpeg', '-y', '-i', video, '-vf', filters+',palettegen', '-frames:v', '1', palette], logs/'palette.log', journal)
    run(['ffmpeg', '-y', '-i', video, '-i', palette, '-lavfi',
         filters+'[x];[x][1:v]paletteuse', '-loop', '0', target], logs/'gif.log', journal)


def orbit_path(capture, output, frames=120):
    import numpy as np
    meta = read_json(capture/'capture.json')
    path = []
    phi = math.radians(15)
    for theta in np.linspace(0, 2*math.pi, frames, endpoint=False):
        position = 4*np.array([math.cos(phi)*math.cos(theta),math.cos(phi)*math.sin(theta),math.sin(phi)])
        z = position/np.linalg.norm(position)
        x = np.cross([0,0,1],z); x /= np.linalg.norm(x)
        y = np.cross(z,x)
        matrix = np.eye(4); matrix[:3,:3] = np.column_stack((x,y,z)); matrix[:3,3] = position
        path.append({'camera_to_world':matrix.reshape(-1).tolist(),
                     'fov':math.degrees(2*math.atan(meta['h']/(2*meta['fl_y'])))})
    save_json(output, {'render_height':512,'render_width':512,'seconds':5,
                       'camera_type':'perspective','camera_path':path})


def postprocess(work, capture, pose_mode, result):
    # Nerfstudio 1.1.5 predates PyTorch 2.6's default change. These checkpoints
    # were generated by this pipeline, so load them using its original format.
    os.environ['TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD']='1'
    journal=result['commands']; logs=work/'logs'
    configs=list((work/'model').rglob('config.yml'))
    if len(configs)!=1: raise RuntimeError(f'Expected one training config, found {len(configs)}')
    config=configs[0];result['config']=str(config)
    run(['ns-eval','--load-config',config,'--output-path',work/'metrics.json'],logs/'eval.log',journal)
    run([sys.executable,PROJECT/'scripts/evaluate_foreground.py','--config',config,'--out',work/'evaluation',
         *(['--reference-capture',capture] if pose_mode=='known' else [])],logs/'foreground_eval.log',journal)
    if pose_mode=='known':
        orbit_path(capture,work/'camera_path.json')
        render_command=['ns-render','camera-path','--load-config',config,'--camera-path-filename',work/'camera_path.json']
    else:
        render_command=['ns-render','interpolate','--load-config',config,'--pose-source','eval',
                        '--interpolation-steps','12','--frame-rate','24']
    run([*render_command,'--output-path',work/'reconstruction.mp4'],logs/'render.log',journal)
    gif_from_video(work/'reconstruction.mp4',work/'reconstruction.gif',logs,journal)
    from PIL import Image
    with Image.open(work/'reconstruction.gif') as gif:
        if getattr(gif,'n_frames',1)<2: raise RuntimeError('GIF is not animated')
    result['metrics']=read_json(work/'metrics.json');result['status']='complete'


def process_object(obj, root, args):
    settings = VARIANTS[args.variant]
    base = args.work / obj['uid']
    work = base / (args.variant if args.pose_mode == 'colmap' else args.variant+'_known')
    if work.exists():
        if args.resume and (work/'result.json').exists() and read_json(work/'result.json').get('status') == 'complete':
            print('SKIP complete', obj['uid'], args.variant)
            return
        if args.retry_failed and (work/'result.json').exists() and read_json(work/'result.json').get('status') == 'failed':
            work.rename(work.with_name(work.name+'_failed_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')))
        else:
            raise FileExistsError(f'Existing unfinished run: {work}. Inspect it before using --retry-failed or a new --work directory.')
    work.mkdir(parents=True)
    logs = work/'logs'
    journal = []
    result = {'uid': obj['uid'], 'variant': args.variant, 'settings': settings,
              'pose_mode': args.pose_mode, 'status': 'running', 'commands': journal}
    try:
        glb = (root / obj['relative_glb']).resolve()
        if not glb.is_relative_to(root.resolve()):
            raise ValueError('GLB resolves outside dataset root')
        result['glb'] = check_glb(glb)
        sha = hashlib.sha256()
        with glb.open('rb') as handle:
            for block in iter(lambda: handle.read(1024*1024), b''):
                sha.update(block)
        result['source_sha256'] = sha.hexdigest()
        capture = base/'capture_512'
        if not (capture/'capture.json').exists():
            run([args.blender, '-b', '-P', PROJECT/'scripts/render_views.py', '--',
                 '--glb', glb, '--out', capture, '--size', '512'], logs/'capture.log', journal)
        chosen = select_images(capture, work/'input', settings['stride'], settings['size'])
        processed = work/'processed'
        sfm_cache = base/'sfm'
        cached = read_json(sfm_cache/'result.json') if (sfm_cache/'result.json').exists() else None
        if args.pose_mode == 'colmap':
            reuse = args.variant in ('baseline','short_training') and cached and cached.get('status') == 'complete'
            if reuse:
                processed.mkdir()
                shutil.copytree(work/'input',processed/'images')
            run(['ns-process-data', 'images', '--data', work/'input', '--output-dir', processed,
                 '--sfm-tool', 'colmap', '--matching-method', 'exhaustive',
                 '--camera-type', 'pinhole', '--num-downscales', '0', '--no-gpu',
                 *(['--skip-colmap','--skip-image-processing','--colmap-model-path',cached['model_path']] if reuse else [])], logs/'sfm.log', journal)
            result['sfm'] = verify_sfm(processed, len(chosen))
            if reuse:
                shutil.copytree(sfm_cache/'matches',work/'matches')
                result['matches'] = cached['matches']
                result['sfm_cache'] = str(sfm_cache/'result.json')
            else:
                result['matches'] = export(processed/'colmap/database.db', processed/'images', work/'matches')
            result['training_images'], result['evaluation_images'] = set_split(processed)
            model_args, parser_args = [], []
        else:
            # Matching remains a real image-based result even when synthetic poses are used.
            # Apt COLMAP often has no CUDA SIFT support; CPU extraction is deliberate.
            processed.mkdir()
            shutil.copytree(work/'input', processed/'images')
            database = processed/'database.db'
            if args.variant in ('baseline','fixed_resolution','short_training') and (sfm_cache/'matches/summary.json').exists():
                shutil.copytree(sfm_cache/'matches',work/'matches')
                result['matches'] = read_json(work/'matches/summary.json')
                result['sfm_cache'] = str(sfm_cache/'result.json')
            else:
                run(['colmap', 'feature_extractor', '--database_path', database,
                     '--image_path', processed/'images', '--ImageReader.single_camera', '1',
                     '--ImageReader.camera_model', 'PINHOLE', '--SiftExtraction.use_gpu', '0',
                     '--SiftExtraction.num_threads', '8'], logs/'features.log', journal)
                run(['colmap', 'exhaustive_matcher', '--database_path', database,
                     '--SiftMatching.use_gpu', '0', '--SiftMatching.num_threads', '8'], logs/'matching.log', journal)
                result['matches'] = export(database, processed/'images', work/'matches')
            result['training_images'], result['evaluation_images'] = known_pose_dataset(capture, chosen, processed, settings['size'])
            model_args = ['--pipeline.model.random-init', 'True', '--pipeline.model.random-scale', '2.0',
                          '--pipeline.model.num-random', '20000']
            parser_args = ['--orientation-method', 'none', '--center-method', 'none',
                           '--auto-scale-poses', 'False', '--scene-scale', '2']
        event_dir = Path('/tmp/assignment2-events')/obj['uid']/(work.name+'_'+uuid.uuid4().hex)
        run(['ns-train', 'splatfacto', '--data', processed, '--output-dir', work/'model',
             '--experiment-name', obj['uid'], '--timestamp', args.variant,
             '--max-num-iterations', settings['steps'], '--viewer.quit-on-train-completion', 'True',
             '--logging.steps-per-log', '100', '--steps-per-save', settings['steps'],
             '--logging.relative-log-dir', event_dir,
             '--vis', 'tensorboard', '--machine.seed', '42',
             '--pipeline.model.background-color', 'white', *model_args,
             '--pipeline.model.num-downscales', settings['downscales'],
             'nerfstudio-data', '--downscale-factor', '1', *parser_args], logs/'train.log', journal)
        if event_dir.exists():
            shutil.copytree(event_dir, logs/'tensorboard')
        postprocess(work,capture,args.pose_mode,result)
    except Exception as error:
        result.update(status='failed', error=str(error), traceback=traceback.format_exc())
        raise
    finally:
        save_json(work/'result.json', result)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--manifest', type=Path, default=PROJECT/'configs/objects.json')
    p.add_argument('--root', type=Path)
    p.add_argument('--work', type=Path, default=PROJECT/'runs')
    p.add_argument('--variant', choices=VARIANTS, default='baseline')
    p.add_argument('--pose-mode', choices=['colmap', 'known'], default='colmap')
    p.add_argument('--only', nargs='*', help='Subset of manifest UIDs for pilot/ablation')
    p.add_argument('--blender', default='blender')
    p.add_argument('--resume', action='store_true')
    p.add_argument('--retry-failed',action='store_true',help='Archive failed run directories before retrying after an inspected fix')
    args = p.parse_args()
    if Path('/usr/local/cuda/bin/nvcc').exists():
        os.environ['PATH'] = '/usr/local/cuda/bin:'+os.environ.get('PATH','')
        os.environ['CUDA_HOME'] = '/usr/local/cuda'
    args.work = args.work.resolve()
    objects = manifest(args.manifest)
    if args.only:
        unknown = set(args.only) - {o['uid'] for o in objects}
        if unknown:
            p.error(f'Unknown UIDs: {unknown}')
        objects = [o for o in objects if o['uid'] in args.only]
    access = probe([args.root] if args.root else ROOTS)
    save_json(args.work/'afs_probe.json', access)
    if access['status'] != 'readable':
        raise RuntimeError('GLB access failed. Inspect afs_probe.json for mount/permissions.')
    for command in (args.blender, 'ns-process-data', 'ns-train', 'ns-render', 'ns-eval', 'colmap', 'ffmpeg'):
        if not shutil.which(command):
            raise RuntimeError(f'Missing executable: {command}')
    failures = []
    for obj in objects:
        try:
            process_object(obj, Path(access['root']), args)
        except Exception as error:
            failures.append({'uid': obj['uid'], 'error': str(error)})
            print('FAILED', obj['uid'], error, file=sys.stderr, flush=True)
    batch_tag = '_'.join(args.only) if args.only else 'all'
    save_json(args.work/f'failures_{args.variant}_{args.pose_mode}_{batch_tag}.json', failures)
    raise SystemExit(1 if failures else 0)


if __name__ == '__main__':
    main()
