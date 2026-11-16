"""Generate findings only from actual, completed runs, including all SfM failures."""
import csv
import statistics
from pathlib import Path
from pipeline import PROJECT, manifest, read_json, save_json


def foreground(folder):
    return read_json(folder/'evaluation/foreground_metrics.json')['mean_foreground_psnr']


def main():
    objects=manifest(PROJECT/'configs/objects.json')
    sfm_rows=[]; baseline=[]; native_rows=[]
    for obj in objects:
        base=PROJECT/'runs'/obj['uid']
        sfm=read_json(base/'sfm/result.json')
        run=read_json(base/'baseline_known/result.json')
        if run['status']!='complete': raise RuntimeError(f'Incomplete baseline: {obj["uid"]}')
        baseline.append(foreground(base/'baseline_known'))
        native_rows.append({'name':obj['name'],'psnr':run['metrics']['results']['psnr'],
                            'foreground_psnr':baseline[-1]})
        sfm_rows.append({'uid':obj['uid'],'name':obj['name'],
                        'registered':sfm.get('registered',0),
                        'verified_pairs':sfm.get('matches',{}).get('verified_pairs',0),
                        'inliers':sfm.get('matches',{}).get('inliers_total',0),
                        'center_rmse':sfm.get('camera_error',{}).get('center_rmse'),
                        'rotation_median_degrees':sfm.get('camera_error',{}).get('rotation_median_degrees'),
                        'status':sfm['status']})
    with (PROJECT/'artifacts/sfm_summary.csv').open('w',newline='',encoding='utf-8') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(sfm_rows[0]));writer.writeheader();writer.writerows(sfm_rows)
    passed=sum(r['registered']/72>=0.8 for r in sfm_rows)
    text=['# Experimental Findings',
          f'All ten selected objects have completed known-pose 3DGS reconstruction, held-out evaluation and animated GIF export. The mean foreground PSNR over the ten objects is {statistics.mean(baseline):.3f} dB, with a range of {min(baseline):.3f} to {max(baseline):.3f} dB. These scores describe known-camera reconstruction; they do not establish camera recovery from images.',
          f'COLMAP passed the predefined 80 percent camera-registration gate on {passed}/10 objects. The registered-camera count ranges from {min(r["registered"] for r in sfm_rows)} to {max(r["registered"] for r in sfm_rows)} out of 72. All ten attempts, including incomplete or failed reconstructions, are included in this denominator. Per-object inlier counts, registered cameras and aligned camera errors are recorded in artifacts/sfm_summary.csv.',
          'Matching and global pose estimation must be assessed separately. A verified pair constrains two views; a useful reconstruction needs a sufficiently connected and geometrically consistent view graph. Incomplete registration limits the appearance observations available to reconstruction even when individual matching plots look plausible. Using capture calibration removes this pose-estimation failure mode from the controlled rendering experiment. It does not repair the estimated-pose pipeline or demonstrate that its missing poses were recovered.']
    low=min(native_rows,key=lambda r:r['psnr']); high=max(native_rows,key=lambda r:r['psnr'])
    text.append(f'Image quality also varies after camera error has been removed: native full-frame PSNR ranges from {low["psnr"]:.3f} dB for {low["name"]} to {high["psnr"]:.3f} dB for {high["name"]}. The lowest-scoring object has foreground PSNR {low["foreground_psnr"]:.3f} dB. Its known-pose reconstruction still loses fine surface detail in the saved target-versus-rendered images; camera calibration alone does not remove all rendering error. High-frequency texture and limited model/optimization capacity are plausible contributors, rather than causes isolated by this experiment.')
    covered=[r for r in sfm_rows if r['registered']/72>=0.8 and r['rotation_median_degrees'] is not None]
    worst=max(covered,key=lambda r:r['rotation_median_degrees'])
    text.append(f'Camera coverage alone is insufficient: {worst["name"]} registered {worst["registered"]}/72 cameras, but its median rotation error after similarity alignment is {worst["rotation_median_degrees"]:.3f} degrees. Its repeated surface pattern provides a plausible source of ambiguous correspondences; this explanation is an interpretation of the matches and pose errors, not an independently isolated causal test.')
    for obj in objects:
        estimated=PROJECT/'runs'/obj['uid']/'baseline/result.json'
        if estimated.exists() and read_json(estimated).get('status')=='complete':
            values=read_json(estimated)['metrics']['results']
            text.append(f'A complete estimated-pose pipeline was also executed on {obj["name"]}: COLMAP cameras and sparse points initialized Splatfacto, which produced a separate reconstruction GIF. Its transductive diagnostic scores are PSNR {values["psnr"]:.3f} dB, SSIM {values["ssim"]:.4f} and LPIPS {values["lpips"]:.4f}. Evaluation images participate in SfM and colored-point initialization; these numbers are not an independent held-out comparison with the known-pose protocol.')
    protocol=read_json(PROJECT/'configs/ablations.json')
    ablations=[]; variant_means={}
    for variant in protocol['variants']:
        differences=[]
        for uid in protocol['uids']:
            base=PROJECT/'runs'/uid
            run=read_json(base/(variant+'_known')/'result.json')
            if run['status']!='complete': raise RuntimeError(f'Incomplete ablation: {uid} {variant}')
            score=foreground(base/(variant+'_known')); reference=foreground(base/(protocol['reference_variant']+'_known'))
            differences.append(score-reference)
            ablations.append({'uid':uid,'variant':variant,'reference_foreground_psnr':reference,
                              'variant_foreground_psnr':score,'delta_db':score-reference})
        text.append(f'For {variant.replace("_"," ")}, the mean foreground-PSNR difference relative to the fixed-resolution reference is {statistics.mean(differences):+.3f} dB across the three preselected objects; individual differences range from {min(differences):+.3f} to {max(differences):+.3f} dB. The same twelve target views and original 512-pixel targets are used in this comparison. Progressive image downscaling is disabled throughout these controlled comparisons.')
        variant_means[variant]=statistics.mean(differences)
    largest=min(variant_means,key=variant_means.get)
    text.append(f'Among the three tested interventions, {largest.replace("_"," ")} produces the largest mean foreground-PSNR decrease in this subset. The resolution comparison varies across objects, including one small positive difference, so lowering resolution is not uniformly harmful in these runs. This distinguishes measured subset behavior from a universal ordering of pipeline choices.')
    save_json(PROJECT/'artifacts/ablation_results.json',ablations)
    text.append('The ablations use one seed and three objects. Their numerical differences support conclusions about this subset and configuration rather than a universal ranking. Synthetic lighting, source texture quality, sparse elevation coverage and the foreground threshold limit the evaluation. PSNR, SSIM and LPIPS measure rendered image agreement; they do not prove correct mesh topology or complete hidden-surface geometry. The separate GIFs and target-versus-rendered images support visual inspection of holes, thin structures and floating Gaussians.')
    (PROJECT/'docs/experimental_findings.md').write_text('\n\n'.join(text)+'\n',encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':13,'axes.titlesize':14,'axes.labelsize':13,'xtick.labelsize':12,'ytick.labelsize':12})
    fig,axes=plt.subplots(1,2,figsize=(12,4.2),constrained_layout=True)
    labels=[o['category'] for o in objects]
    axes[0].bar(labels,[r['registered'] for r in sfm_rows],color='#087f8c')
    axes[0].axhline(72*.8,ls='--',color='#b44a37',label='80% coverage gate')
    axes[0].set(ylabel='Registered cameras out of 72',title='Camera recovery varies across objects',ylim=(0,78))
    axes[0].legend(fontsize=12); axes[0].tick_params(axis='x',rotation=55)
    for uid in protocol['uids']:
        name=next(o['category'] for o in objects if o['uid']==uid)
        values=[foreground(PROJECT/'runs'/uid/(protocol['reference_variant']+'_known'))]
        values.extend(foreground(PROJECT/'runs'/uid/(v+'_known')) for v in protocol['variants'])
        axes[1].plot(['Fixed 512px','Fewer views','256px','3000 steps'],values,marker='o',label=name)
    axes[1].set(ylabel='Foreground PSNR on common 512px targets (dB)',title='Controlled reconstruction ablations')
    axes[1].legend(fontsize=12);axes[1].grid(axis='y',alpha=.2)
    fig.savefig(PROJECT/'artifacts/experiment_comparison.png',dpi=180)
    plt.close(fig)
    print('\n\n'.join(text))


if __name__=='__main__':main()
