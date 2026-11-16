"""Read an actual GLB under the current account; never modifies source data."""
import argparse
import json
import os
import struct
from pathlib import Path

ROOTS = [Path('/mnt/afs/260010017/data/objaverse/glbs'),
         Path('/afs/260010017/data/objaverse/glbs')]


def check_glb(path):
    path = Path(path)
    with path.open('rb') as f:
        header = f.read(12)
    if len(header) != 12:
        raise ValueError(f'Truncated GLB: {path}')
    magic, version, size = struct.unpack('<4sII', header)
    if magic != b'glTF' or version != 2 or size != path.stat().st_size:
        raise ValueError(f'Invalid GLB v2 header/length: {path}')
    return {'path': str(path), 'magic': 'glTF', 'version': version, 'bytes': size}


def probe(roots):
    attempts = []
    for root in map(Path, roots):
        try:
            root.stat()  # Unlike exists(), preserves permission errors.
            def onerror(error):
                raise error
            found = None
            for directory, _, files in os.walk(root, onerror=onerror):
                found = next((Path(directory) / n for n in sorted(files)
                              if n.lower().endswith('.glb')), None)
                if found:
                    break
            if not found:
                raise FileNotFoundError(f'No GLB below {root}')
            result = check_glb(found)
            return {'status': 'readable', 'root': str(root), 'sample': result,
                    'uid': getattr(os, 'getuid', lambda: None)(), 'attempts': attempts}
        except (OSError, ValueError) as error:
            attempts.append({'root': str(root), 'error': type(error).__name__,
                             'message': str(error)})
    return {'status': 'unavailable', 'attempts': attempts}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', action='append')
    parser.add_argument('--output', type=Path, default=Path('artifacts/afs_probe.json'))
    args = parser.parse_args()
    result = probe(args.root or ROOTS)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'readable' else 2)
