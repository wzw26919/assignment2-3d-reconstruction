"""Contact sheet of INPUT views; never labeled as reconstructed output."""
from PIL import Image, ImageDraw, ImageFont
from pipeline import PROJECT, read_json

objects=read_json(PROJECT/'configs/objects.json')['objects']
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',14)
canvas=Image.new('RGB',(1100,600),'white')
draw=ImageDraw.Draw(canvas)
draw.text((15,10),'INPUT VIEWS - ten Assignment 1 objects (not reconstructions)',font=font,fill='#142b43')
for index,obj in enumerate(objects):
    source=PROJECT/'runs'/obj['uid']/'capture_512/r1_003.png'
    image=Image.open(source).convert('RGB').resize((220,220))
    x=(index%5)*220; y=40+(index//5)*280
    canvas.paste(image,(x,y))
    draw.text((x+8,y+222),obj['name'][:26],font=font,fill='#142b43')
    draw.text((x+8,y+242),obj['uid'][:12],font=font,fill='#555555')
canvas.save(PROJECT/'artifacts/input_contact_sheet.jpg',quality=95)
