"""Preserve attribution from dataset metadata for the selected ten source objects."""
import gzip
import json
from pathlib import Path

from pipeline import PROJECT, read_json, save_json


def main():
    objects = read_json(PROJECT/'configs/objects.json')['objects']
    cache, output = {}, []
    for obj in objects:
        chunk = Path(obj['relative_glb']).parts[0]
        if chunk not in cache:
            with gzip.open(f'/mnt/afs/260010017/data/objaverse/metadata/{chunk}.json.gz','rt') as handle:
                cache[chunk] = json.load(handle)
        metadata = cache[chunk][obj['uid']]
        output.append({'uid':obj['uid'],'name':metadata.get('name'),
                       'author':metadata.get('user'), 'license':metadata.get('license'),
                       'source_url':metadata.get('viewerUrl') or 'https://sketchfab.com/3d-models/'+obj['uid']})
    save_json(PROJECT/'artifacts/object_attribution.json', output)


if __name__ == '__main__':
    main()
