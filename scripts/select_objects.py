"""Select diverse textured objects only from Assignment 1's final keep set."""
import csv
import hashlib
import json
import re
from pathlib import Path

DATASET = Path('/mnt/afs/260010017/data/objaverse')
GROUPS = {
    'chair': r'\bchair\b', 'shoe': r'\b(shoe|sneaker|boot)\b',
    'toy': r'\b(teddy|toy|plush|figurine)\b', 'vehicle': r'\b(car|truck|van)\b',
    'container': r'\b(vase|teapot|jug)\b', 'camera': r'\b(camera|radio)\b',
    'food': r'\b(bread|cake|burger|apple)\b', 'bag': r'\b(bag|backpack|suitcase)\b',
    'statue': r'\b(statue|sculpture|bust)\b', 'instrument': r'\b(guitar|violin|piano)\b',
}


def number(row, key):
    try:
        return float(row[key])
    except (ValueError, KeyError):
        return 0


def main():
    final = Path((DATASET/'cleaning/FINAL_OUTPUT_CURRENT.txt').read_text().strip())
    keep = set((final/'keep_uids.txt').read_text().split())
    with (final/'labels.csv').open() as handle:
        rows = list(csv.DictReader(handle))
    valid = [r for r in rows if r['uid'] in keep and r['keep'].lower() == 'true'
             and r['feature_complete'].lower() == 'true' and r['load_ok'].lower() == 'true'
             and r['draco'].lower() != 'true' and number(r, 'n_animations') == 0
             and number(r, 'n_mat_basecolor_tex') > 0 and number(r, 'tex_loaded') > 0
             and 2000 <= number(r, 'n_faces') <= 150000
             and number(r, 'flatness') >= 0.15 and number(r, 'file_size') < 25000000
             and r['license'] in ('by', 'by-sa', 'cc0')]
    chosen, candidates = [], {}
    used = set()
    for category, pattern in GROUPS.items():
        pool = [r for r in valid if re.search(pattern, r['name'].lower()) and r['uid'] not in used]
        pool.sort(key=lambda r: (-number(r, 'clip_object'), -number(r, 'tex_color_std'), r['uid']))
        candidates[category] = [{k: r[k] for k in ('uid', 'name', 'chunk', 'license', 'n_faces', 'clip_object', 'tex_color_std')} for r in pool[:6]]
        if not pool:
            raise RuntimeError(f'No candidates for {category}')
        obj = pool[0]
        used.add(obj['uid'])
        chosen.append({'uid': obj['uid'], 'name': obj['name'], 'category': category,
                       'relative_glb': f"{obj['chunk']}/{obj['uid']}.glb", 'license': obj['license'],
                       'selection_reason': f'Assignment 1 keep set; static textured mesh; representative {category}',
                       'assignment1_row': obj})
    result = {'assignment1_manifest': str(final/'keep_uids.txt'),
              'assignment1_manifest_sha256': hashlib.sha256((final/'keep_uids.txt').read_bytes()).hexdigest(),
              'selection_protocol': 'Fixed category keywords and deterministic CLIP-object ranking before reconstruction; no result-based replacements.',
              'objects': chosen}
    Path('configs').mkdir(exist_ok=True)
    Path('artifacts').mkdir(exist_ok=True)
    Path('configs/objects.json').write_text(json.dumps(result, indent=2, ensure_ascii=False))
    Path('artifacts/selection_candidates.json').write_text(json.dumps(candidates, indent=2, ensure_ascii=False))
    print(json.dumps(candidates, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
