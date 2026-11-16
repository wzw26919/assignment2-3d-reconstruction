"""Supplement full-frame ns-eval with a documented foreground error measure."""
import argparse
import json
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from nerfstudio.utils.eval_utils import eval_setup


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--reference-capture', type=Path)
    args = p.parse_args()
    _, pipeline, _, _ = eval_setup(args.config, test_mode='test')
    dataset = pipeline.datamanager.eval_dataset
    args.out.mkdir(parents=True, exist_ok=True)
    rows = []
    with torch.no_grad():
        for index in range(len(dataset)):
            camera = dataset.cameras[index:index+1].to(pipeline.device)
            predicted = pipeline.model.get_outputs_for_camera(camera)['rgb'].clamp(0,1)
            target = dataset[index]['image'].to(predicted.device)[...,:3]
            if args.reference_capture:
                # Compare all resolution variants against the SAME original 512px GT.
                filename = Path(dataset.image_filenames[index]).name
                target = torch.from_numpy(np.asarray(Image.open(args.reference_capture/filename).convert('RGB')).copy()).to(predicted.device).float()/255
                predicted = torch.nn.functional.interpolate(predicted.permute(2,0,1)[None],
                    size=target.shape[:2],mode='bilinear',align_corners=False)[0].permute(1,2,0)
            mask = (target-1).abs().amax(dim=-1) > 0.08
            if mask.sum() == 0:
                raise RuntimeError('No foreground detected against white background')
            mse = ((predicted-target)**2)[mask].mean().item()
            rows.append({'index':index,'file':str(dataset.image_filenames[index]),
                         'foreground_fraction':mask.float().mean().item(),
                         'reference_full_psnr':float(-10*np.log10(max(((predicted-target)**2).mean().item(),1e-12))),
                         'foreground_mse':mse,'foreground_psnr':float(-10*np.log10(max(mse,1e-12)))})
            rgb = (predicted.cpu().numpy()*255).astype(np.uint8)
            gt = (target.cpu().numpy()*255).astype(np.uint8)
            pair = np.concatenate((gt,rgb),axis=1)
            Image.fromarray(pair).save(args.out/f'view_{index:03d}.png')
    summary = {'definition':'GT pixels with max absolute RGB difference from white > 0.08; near-white object regions may be excluded.',
               'mean_foreground_psnr':float(np.mean([r['foreground_psnr'] for r in rows])),
               'mean_reference_full_psnr':float(np.mean([r['reference_full_psnr'] for r in rows])),
               'views':rows}
    (args.out/'foreground_metrics.json').write_text(json.dumps(summary,indent=2))


if __name__ == '__main__':
    main()
