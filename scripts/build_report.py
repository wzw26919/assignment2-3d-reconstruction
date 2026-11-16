"""Create a PDF from the finalized methods and actual exported results."""
import argparse
import csv
import html
import json
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                               TableStyle, Image, PageBreak, KeepTogether, Flowable)

PROJECT=Path(__file__).resolve().parents[1]
NAVY=colors.HexColor('#142b43'); TEAL=colors.HexColor('#087f8c')


class SubmissionFields(Flowable):
    """Blank, editable submission metadata supplied by the actual group."""
    def __init__(self,width):
        super().__init__();self.width=width;self.height=164
    def draw(self):
        canvas=self.canv;canvas.setFont('Helvetica',8);canvas.setFillColor(NAVY)
        for name,label,y,height in [
            ('group_number','Group number',131,17),
            ('repository_url','GitHub repository URL',103,17),
            ('member_names','Group member names',75,17),
            ('member_contributions','Each member contribution',18,45)]:
            canvas.drawString(0,y+height+3,label)
            canvas.acroForm.textfield(name=name,tooltip=label,x=0,y=y,width=self.width,
                height=height,value='',fontName='Helvetica',fontSize=8,borderWidth=.5,
                borderColor=colors.HexColor('#aebecb'),fillColor=colors.HexColor('#f8fafc'),
                textColor=NAVY,fieldFlags='multiline' if height>20 else '',relative=True)


def inline(text):
    text=html.escape(text)
    text=re.sub(r'`([^`]+)`',r'<font name="Courier" size="8">\1</font>',text)
    text=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',text)
    text=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',r'<link href="\2" color="#087f8c">\1</link>',text)
    return text.replace('−','-').replace('—','-').replace('–','-')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--submission',type=Path,default=PROJECT/'submission')
    p.add_argument('--out',type=Path,default=PROJECT/'output/pdf/assignment2_report.pdf')
    args=p.parse_args()
    complete=json.loads((args.submission/'completion.json').read_text())
    if complete['objects']!=10: raise ValueError('Ten complete reconstructions required')
    args.out.parent.mkdir(parents=True,exist_ok=True)
    styles=getSampleStyleSheet()
    body=ParagraphStyle('Body',fontName='Helvetica',fontSize=9.5,leading=13.5,
                        textColor=NAVY,spaceAfter=8,splitLongWords=True)
    heading=ParagraphStyle('Section',parent=body,fontName='Helvetica-Bold',fontSize=14,
                           leading=19,spaceBefore=15,spaceAfter=7,keepWithNext=True,textColor=TEAL)
    small=ParagraphStyle('Small',parent=body,fontSize=7.8,leading=10.5)
    title=ParagraphStyle('ReportTitle',parent=body,fontName='Helvetica-Bold',fontSize=25,leading=29,spaceAfter=16)
    width=A4[0]-84
    story=[Paragraph('3D Reconstruction<br/>and Rendering',title),
           Paragraph('Assignment 2 | Objaverse | COLMAP and 3D Gaussian Splatting',body),
           Paragraph('Ten reconstructed objects with saved feature matches, held-out evaluations and GIF animations.',body),
           Paragraph('Complete the editable group and repository fields below before submission.',small),
           SubmissionFields(width),Spacer(1,10)]
    sheet=args.submission/'artifacts/input_contact_sheet.jpg'
    if sheet.exists(): story.extend([Image(str(sheet),width=width,height=width*600/1100),Spacer(1,14)])
    story.append(PageBreak())
    text=(args.submission/'docs/pipeline_documentation.md').read_text(encoding='utf-8')
    lines=text.splitlines(); i=0
    while i<len(lines):
        line=lines[i].strip()
        if line=='## Submission information':
            i+=1
            while i<len(lines) and not lines[i].startswith('## '): i+=1
            continue
        if not line or line.startswith('# '): i+=1;continue
        if line.startswith('## '):
            story.append(Paragraph(inline(line[3:]),heading));i+=1;continue
        if line.startswith('- '):
            story.append(Paragraph('&bull; '+inline(line[2:]),body));i+=1;continue
        if line.startswith('|'):
            raw=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=[v.strip() for v in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r'[-: ]+',c) for c in row): raw.append(row)
                i+=1
            table=Table([[Paragraph(inline(c),small) for c in row] for row in raw],
                        colWidths=[width/len(raw[0])]*len(raw[0]),repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f2f4')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('BOTTOMPADDING',(0,0),(-1,-1),7),
                ('TOPPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),0.6,TEAL),
                ('LINEBELOW',(0,1),(-1,-1),0.2,colors.HexColor('#d7dfe5'))]))
            story.extend([table,Spacer(1,10)]);continue
        paragraph=[]
        while i<len(lines) and lines[i].strip() and not lines[i].startswith('#') and not lines[i].strip().startswith('|'):
            paragraph.append(lines[i].strip());i+=1
        story.append(Paragraph(inline(' '.join(paragraph)),body))
    story.extend([PageBreak(),Paragraph('Measured reconstruction results',heading),
                  Paragraph('The primary ten-object results below use known synthetic camera poses. The separately reported COLMAP pilot uses transductive geometry and color initialization.',body)])
    with (args.submission/'results.csv').open(encoding='utf-8') as handle: rows=list(csv.DictReader(handle))
    table_rows=[['Object','PSNR','SSIM','LPIPS','FG PSNR']]
    for row in rows:
        table_rows.append([row['name'],*[f"{float(row.get(k,0)):.3f}" for k in ('psnr','ssim','lpips','foreground_psnr')]])
    table=Table([[Paragraph(html.escape(c),small) for c in row] for row in table_rows],
                colWidths=[width*.44,*([width*.14]*4)],repeatRows=1)
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e8f2f4')),
          ('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),
          ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f5f7fa')])]))
    story.extend([table,Spacer(1,14),Paragraph('PSNR and foreground PSNR are measured in dB. SSIM is higher-is-better; LPIPS is lower-is-better. The experiment protocol and foreground approximation are described in the methods.',body)])
    measured=args.submission/'docs/experimental_findings.md'
    if measured.exists():
        story.append(Paragraph('Analysis of measured outcomes',heading))
        for paragraph in measured.read_text(encoding='utf-8').split('\n\n'):
            if paragraph.strip() and not paragraph.startswith('#') and not paragraph.startswith('|'):
                story.append(Paragraph(inline(paragraph.replace('\n',' ')),body))
    chart=args.submission/'artifacts/experiment_comparison.png'
    if chart.exists():
        story.extend([Spacer(1,10),Image(str(chart),width=width,height=width*4.2/12)])
    for start in range(0,len(rows),4):
        story.extend([PageBreak(),Paragraph('Held-out views and verified matches',heading),
                      Paragraph('Each tile shows a held-out target image on the left and its reconstructed rendering on the right, followed by an actual COLMAP matching pair. GIF animations are supplied separately in the results gallery.',small)])
        tiles=[]
        for row in rows[start:start+4]:
            base=args.submission/'results'/row['uid']; cell_width=(width-14)/2
            content=[Paragraph(html.escape(row['name']),ParagraphStyle('TileTitle',parent=body,fontName='Helvetica-Bold',fontSize=9,leading=12)),
                     Image(str(base/'evaluation/view_000.png'),width=cell_width,height=cell_width/2),
                     Spacer(1,3)]
            match=base/'matches/matches_00.png'
            if match.exists():
                from PIL import Image as PILImage
                with PILImage.open(match) as im: h=cell_width*im.height/im.width
                content.append(Image(str(match),width=cell_width,height=h))
            content.extend([Paragraph(f"PSNR {float(row['psnr']):.2f} dB | foreground {float(row['foreground_psnr']):.2f} dB",small),Spacer(1,12)])
            tiles.append(content)
        while len(tiles)%2: tiles.append([])
        grid=Table([tiles[i:i+2] for i in range(0,len(tiles),2)],colWidths=[width/2]*2)
        grid.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),10)]))
        story.append(grid)
    def decorate(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#d7dfe5'));canvas.line(42,37,A4[0]-42,37)
        canvas.setFont('Helvetica',8);canvas.setFillColor(NAVY)
        canvas.drawString(42,24,'Assignment 2 | Objaverse 3D reconstruction')
        canvas.drawRightString(A4[0]-42,24,str(doc.page))
    document=SimpleDocTemplate(str(args.out),pagesize=A4,rightMargin=42,leftMargin=42,
                               topMargin=38,bottomMargin=48,title='Assignment 2 - 3D Reconstruction and Rendering',author='Course project group')
    document.build(story,onFirstPage=decorate,onLaterPages=decorate)
    print(args.out)


if __name__=='__main__':main()
