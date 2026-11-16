"""Add integrity checks and refresh the final ZIP after PDF visual verification."""
import argparse
import hashlib
import zipfile
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--submission',type=Path,default=PROJECT/'submission')
    args=p.parse_args()
    if not (args.submission/'assignment2_report.pdf').is_file():
        raise FileNotFoundError('Copy the visually verified report PDF into the submission first')
    sums=[]
    for file in sorted(args.submission.rglob('*')):
        if file.is_file() and file.name!='SHA256SUMS.txt':
            with file.open('rb') as handle: digest=hashlib.file_digest(handle,'sha256').hexdigest()
            sums.append(digest+'  '+file.relative_to(args.submission).as_posix())
    (args.submission/'SHA256SUMS.txt').write_text('\n'.join(sums)+'\n',encoding='utf-8')
    archive=args.submission.with_suffix('.zip')
    temporary=archive.with_suffix('.zip.tmp')
    with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as handle:
        for file in sorted(args.submission.rglob('*')):
            if file.is_file(): handle.write(file,file.relative_to(args.submission.parent))
    temporary.replace(archive)
    with zipfile.ZipFile(archive) as handle:
        if handle.testzip(): raise ValueError('ZIP integrity check failed')
    print(archive)


if __name__=='__main__':main()
