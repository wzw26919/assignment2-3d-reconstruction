"""Check real animation files and create angle sheets for visual inspection."""
import json
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pipeline import PROJECT, manifest, read_json, save_json

objects=manifest(PROJECT/'configs/objects.json')
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
rows=[]
for start in (0,5):
    canvas=Image.new('RGB',(1040,1120),'white');draw=ImageDraw.Draw(canvas)
    draw.text((12,10),'TRAINED 3DGS - four orbit angles per object',font=font,fill='#142b43')
    for i,obj in enumerate(objects[start:start+5]):
        folder=PROJECT/'runs'/obj['uid']/'baseline_known'
        if read_json(folder/'result.json')['status']!='complete': raise RuntimeError('Incomplete baseline')
        with Image.open(folder/'reconstruction.gif') as gif:
            if gif.n_frames<2 or gif.info.get('loop')!=0: raise ValueError('Invalid looping animation')
            samples=[]
            for j,index in enumerate((0,gif.n_frames//4,gif.n_frames//2,3*gif.n_frames//4)):
                gif.seek(index);image=gif.convert('RGB')
                mask=np.max(np.abs(np.asarray(image,dtype=float)/255-1),axis=-1)>.08
                fraction=float(mask.mean());samples.append(fraction)
                if fraction<.001: raise ValueError(f'Blank rendering: {obj["uid"]} frame {index}')
                canvas.paste(image.resize((220,220)),(160+j*220,30+i*218))
            draw.text((8,65+i*218),obj['category'],font=font,fill='#142b43')
            draw.text((8,87+i*218),obj['uid'][:12],font=font,fill='#555555')
            rows.append({'uid':obj['uid'],'frames':gif.n_frames,'size':list(gif.size),
                         'foreground_fractions':samples})
    canvas.save(PROJECT/'artifacts'/f'reconstruction_angles_{start//5+1}.jpg',quality=95)
save_json(PROJECT/'artifacts/animation_checks.json',rows)
print('10 looping GIFs validated; inspect both angle sheets visually.')
