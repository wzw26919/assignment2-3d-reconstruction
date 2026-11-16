"""Export COLMAP verified correspondences, all pair counts, and representative plots."""
import argparse
import csv
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

MAX_IMAGE_ID = 2147483647


def decode_pair(pair_id):
    return pair_id // MAX_IMAGE_ID, pair_id % MAX_IMAGE_ID


def export(database, images, out, max_plots=8):
    database, images, out = map(Path, (database, images, out))
    out.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(f'{database.resolve().as_uri()}?mode=ro', uri=True)) as conn:
        names = dict(conn.execute('SELECT image_id, name FROM images'))
        keys = {i: np.frombuffer(data, np.float32).reshape(rows, cols)[:, :2].copy()
                for i, rows, cols, data in conn.execute('SELECT image_id,rows,cols,data FROM keypoints')}
        raw = dict(conn.execute('SELECT pair_id,rows FROM matches'))
        records = list(conn.execute('SELECT pair_id,rows,cols,data,config FROM two_view_geometries'))
    csv_rows, verified = [], {}
    for pair_id, rows, cols, data, config in records:
        i, j = decode_pair(pair_id)
        csv_rows.append({'image1': names[i], 'image2': names[j],
                         'raw_matches': raw.get(pair_id, 0), 'inliers': rows,
                         'inlier_ratio': rows / max(1, raw.get(pair_id, 0)), 'config': config})
        if rows:
            verified[str(pair_id)] = np.frombuffer(data, np.uint32).reshape(rows, cols).copy()
    with (out / 'pairs.csv').open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['image1', 'image2', 'raw_matches', 'inliers', 'inlier_ratio', 'config'])
        writer.writeheader()
        writer.writerows(csv_rows)
    # Original coordinates + feature indices allow reproducing every plot/pair.
    np.savez_compressed(out / 'keypoints.npz', **{str(i): v for i, v in keys.items()})
    np.savez_compressed(out / 'verified_matches.npz', **verified)
    (out / 'image_ids.json').write_text(json.dumps(names, indent=2), encoding='utf-8')
    ranked = sorted((r for r in records if r[1] > 0), key=lambda r: r[1])
    # Evenly sample low/medium/high match counts, instead of showing only best pairs.
    indices = np.unique(np.linspace(0, len(ranked)-1, min(max_plots, len(ranked)), dtype=int)) if ranked else []
    for number, index in enumerate(indices):
        pair_id, rows, _, _, _ = ranked[index]
        i, j = decode_pair(pair_id)
        left = Image.open(images / names[i]).convert('RGB')
        right = Image.open(images / names[j]).convert('RGB')
        canvas = Image.new('RGB', (left.width + right.width, max(left.height, right.height) + 30), 'white')
        canvas.paste(left, (0, 30)); canvas.paste(right, (left.width, 30))
        draw = ImageDraw.Draw(canvas)
        draw.text((8, 8), f'{names[i]} / {names[j]}   geometric inliers={rows}', fill='black')
        matches = verified[str(pair_id)]
        for k in np.linspace(0, rows-1, min(120, rows), dtype=int):
            a, b = matches[k]
            x1, y1 = keys[i][a]; x2, y2 = keys[j][b]
            draw.line((float(x1), float(y1+30), float(x2+left.width), float(y2+30)), fill='#21baa8', width=1)
        canvas.save(out / f'matches_{number:02d}.png')
    summary = {'images': len(names), 'verified_pairs': len(verified),
               'inliers_total': sum(r['inliers'] for r in csv_rows),
               'pair_count': len(records), 'plots': len(indices)}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--database', type=Path, required=True)
    p.add_argument('--images', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    print(export(args.database, args.images, args.out))
