"""Build the course report with the official ICLR 2027 LaTeX style.

The official style is kept unchanged. The document overrides the conference
publication header, because this is coursework rather than an ICLR paper.
Requires Tectonic (or compile docs/latex/report.tex with another TeX engine).
"""
import argparse
import csv
import json
import shutil
import subprocess
from pathlib import Path

from pypdf import PdfReader, PdfWriter

PROJECT = Path(__file__).resolve().parents[1]


def escape(value):
    mapping = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%",
               "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
               "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return ''.join(mapping.get(c, c) for c in str(value))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tectonic', default='tectonic')
    parser.add_argument('--out', type=Path, default=PROJECT/'output/pdf')
    args = parser.parse_args()
    source = PROJECT/'docs/latex'
    source.mkdir(parents=True, exist_ok=True)
    result_file = PROJECT/'results.csv'
    if not result_file.exists():
        result_file = PROJECT/'submission/results.csv'
    with result_file.open(encoding='utf-8') as handle:
        rows = list(csv.DictReader(handle))
    with (PROJECT/'artifacts/sfm_summary.csv').open(encoding='utf-8') as handle:
        sfm = {row['uid']: row for row in csv.DictReader(handle)}
    team = json.loads((PROJECT/'configs/team.json').read_text(encoding='utf-8'))
    repository = team.get('repository_url') or ''
    table_rows = []
    for row in rows:
        label = {'SUZILAJ@J-01 Flower Vase': 'Flower Vase / basket',
                 'Character Dev Boot Asset': 'Boot',
                 'Toy Car_free model': 'Toy car',
                 'Globe sculpture, San Francisco': 'Globe sculpture',
                 'My First 3D Model - Guitar': 'Guitar'}.get(row['name'], row['name'])
        table_rows.append(escape(label) + ' & ' + sfm[row['uid']]['registered'] + '/72 & '
                          + ' & '.join(f"{float(row[key]):.3f}" for key in
                                       ('psnr', 'ssim', 'lpips', 'foreground_psnr')) + r' \\')
    gallery = []
    for start in range(0, len(rows), 4):
        gallery.append(r'\clearpage\section*{Reconstruction and matching evidence' +
                       (f' ({start//4+1}/3)' if len(rows)>4 else '') + '}' + '\n' +
                       r'Each object shows a held-out target (left) and a trained 3DGS rendering (right), followed by an actual geometrically verified matching pair. Full correspondences and looping GIFs are in the repository.\par\medskip')
        for row in rows[start:start+4]:
            uid = row['uid']
            gallery.append(r'\noindent\begin{minipage}[t]{0.48\linewidth}' + '\n' +
                           r'\textbf{' + escape(row['name']) + r'}\par\smallskip' + '\n' +
                           r'\includegraphics[width=\linewidth]{results/' + uid + r'/evaluation/view_000.png}\par' + '\n' +
                           r'\includegraphics[width=\linewidth]{results/' + uid + r'/matches/matches_00.png}\par' + '\n' +
                           r'{\footnotesize PSNR ' + f"{float(row['psnr']):.2f}" +
                           r' dB; foreground ' + f"{float(row['foreground_psnr']):.2f}" +
                           r' dB.}\end{minipage}\hfill' + '\n')
            if (rows.index(row)-start) % 2 == 1:
                gallery.append(r'\par\bigskip' + '\n')
    template = (source/'report_body.tex').read_text(encoding='utf-8')
    template = template.replace('@@RESULT_ROWS@@', '\n'.join(table_rows))
    template = template.replace('@@GALLERY@@', ''.join(gallery))
    template = template.replace('@@REPOSITORY@@', escape(repository))
    (source/'report.tex').write_text(template, encoding='utf-8')
    args.out.mkdir(parents=True, exist_ok=True)
    command = [str(Path(args.tectonic).resolve()) if Path(args.tectonic).exists() else args.tectonic,
               '--keep-logs', '--outdir', str(args.out.resolve()), 'report.tex']
    subprocess.run(command, cwd=source, check=True)
    final = args.out/'assignment2_report.pdf'
    reader = PdfReader(args.out/'report.pdf')
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    fields = reader.get_fields() or {}
    values = {name: field.get('/V', '') for name, field in fields.items()}
    if set(values) != {'groupnumber', 'repositoryurl', 'membernames', 'membercontributions'}:
        raise ValueError('Expected four editable submission fields')
    writer.update_page_form_field_values(None, values, auto_regenerate=False)
    with final.open('wb') as handle:
        writer.write(handle)
    reopened = PdfReader(final)
    assert reopened.get_fields()['repositoryurl']['/V'] == repository
    for page in reopened.pages:
        for annotation in page.get('/Annots', []):
            widget = annotation.get_object()
            if widget.get('/Subtype') == '/Widget':
                assert widget.get('/AP', {}).get('/N')
    print(final)


if __name__ == '__main__':
    main()
