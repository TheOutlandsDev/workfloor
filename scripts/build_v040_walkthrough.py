"""Build an 84-second edited, captioned walkthrough from verified UI captures.

Developer tools: Pillow and an independently installed FFmpeg with libx264.
The application and source release need neither dependency. Captures stay intact;
frames letterbox them or use the explicitly recorded top-detail crop.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageDraw, ImageFont

SOURCE = '6a7a02ade5b01e1a6fc76f6e87a40ac7d2c24af6'
SCENES = (
    ('01-baseline.jpg', 'Begin with a known result',
     '9 orders / 365 units / 4 delayed',
     'The default due-date report starts with invented work orders. No CSV has been imported.',
     'Check the starting point before changing the dataset.', (0,430)),
    ('02-valid-preview.jpg', 'Preview before writing',
     '3 records / 3 valid / 0 issues',
     'Load the included synthetic sample and inspect every row. Preview leaves the report at nine orders.',
     'All rows must pass. Apply is a separate, explicit action.', (600,936)),
    ('03-import-history.jpg', 'Commit the orders and receipt together',
     '12 orders / 6 delayed / 1 stored receipt',
     'Apply adds three orders and two completion events. Their receipt commits in the same SQLite transaction.',
     'If receipt storage fails, the whole import rolls back.', None),
    ('04-receipt.jpg', 'Inspect the stored explanation',
     'File hash / order IDs / counts / source fingerprints',
     'View the saved receipt and download its exact JSON bytes. Raw CSV contents and filenames are not stored.',
     'The displayed ID and time are fixed fictional capture fixtures.', None),
    ('05-after-restart.jpg', 'Restart the app; reopen the receipt',
     'New Python process / same data directory',
     'The original app process stops. A new process opens the same database and downloads the identical receipt.',
     'The browser download bytes match the first download exactly.', None),
    ('06-after-restore.jpg', 'Restore into a fresh directory',
     'Verified backup / new data directory / same receipt bytes',
     'Stop the app, back up, verify and restore with the CLI. Reopen the new copy and download the receipt again.',
     'This is local history, not a signed audit log or a power-loss guarantee.', None),
)


def sha(data): return hashlib.sha256(data).hexdigest()


def stamp(seconds): return '00:%02d:%02d.000' % (seconds // 60, seconds % 60)


def build(captures, output, ffmpeg, regular, bold):
    if not output.is_absolute() or output.exists(): raise ValueError('Choose a new absolute output directory')
    record_bytes=(captures/'capture.json').read_bytes(); record=json.loads(record_bytes)
    if record['status']!='PASS' or record['source_revision']!=SOURCE or not record['synthetic_only'] or len(record['checks'])!=8: raise ValueError('Verified v0.4 capture record required')
    rows={r['filename']:r for r in record['images']}
    if set(rows)!={s[0] for s in SCENES}: raise ValueError('Exact capture set required')
    for name,row in rows.items():
        data=(captures/name).read_bytes()
        if len(data)!=row['bytes'] or sha(data)!=row['sha256']: raise ValueError('Capture bytes differ')
    output.mkdir(); frames=output/'frames'; frames.mkdir()
    fonts={k:ImageFont.truetype(str(path),size) for k,path,size in [('title',bold,36),('text',regular,24),('small',regular,18),('metric',bold,23)]}
    def wrapped(draw, text, xy, font, fill, width, max_lines=3):
        words=text.split(); lines=[]; line=''
        for word in words:
            test=(line+' '+word).strip()
            if draw.textlength(test,font=font)>width:
                if not line: raise ValueError('Unbreakable caption')
                lines.append(line); line=word
            else: line=test
        if line: lines.append(line)
        if len(lines)>max_lines: raise ValueError('Caption exceeds frame budget')
        x,y=xy
        for i,line in enumerate(lines): draw.text((x,y+i*(font.size+7)),line,font=font,fill=fill)
        return y+len(lines)*(font.size+7)
    concat=['ffconcat version 1.0']; vtt=['WEBVTT','']; chapters=[]
    for i,(name,title,metric,caption,note,crop) in enumerate(SCENES):
        image=Image.new('RGB',(1280,900),'#101d23'); draw=ImageDraw.Draw(image)
        draw.rectangle((0,0,1280,7),fill='#c5ebaa')
        draw.text((32,25),'OUTLANDS / WORKFLOOR v0.4.1',font=fonts['small'],fill='#c5ebaa')
        draw.text((1080,25),f'{i+1:02d} / 06',font=fonts['small'],fill='#a4b7be')
        draw.text((32,58),title,font=fonts['title'],fill='#f3f5ed')
        wrapped(draw,metric,(32,111),fonts['metric'],'#c5ebaa',1216,max_lines=1)
        with Image.open(captures/name) as original:
            ui=original.convert('RGB')
            if crop: ui=ui.crop((0,crop[0],ui.width,min(crop[1],ui.height)))
            factor=min(1216/ui.width,542/ui.height)
            ui=ui.resize((round(ui.width*factor),round(ui.height*factor)),Image.Resampling.LANCZOS)
            x=32+(1216-ui.width)//2; y=166+(542-ui.height)//2
            draw.rounded_rectangle((31,165,1249,709),radius=8,fill='#091216',outline='#34464d',width=1)
            image.paste(ui,(x,y))
        bottom=wrapped(draw,caption,(32,731),fonts['text'],'#f3f5ed',1216,max_lines=2)
        wrapped(draw,note,(32,bottom+6),fonts['small'],'#a4b7be',1216,max_lines=2)
        draw.text((32,865),'ACTUAL UI CAPTURES / EDITED STEPS / SYNTHETIC DATA / NO AUDIO',font=fonts['small'],fill='#c5ebaa')
        frame=f'{i+1:02d}.png'; image.save(frames/frame)
        concat += [f"file 'frames/{frame}'",'duration 14']
        start,end=i*14,(i+1)*14
        vtt += [stamp(start)+' --> '+stamp(end),title,caption,note,'']
        chapters.append(dict(start_seconds=start,end_seconds=end,title=title,capture=name,crop_vertical_range=crop,caption=caption,note=note))
    concat.append("file 'frames/06.png'")
    with Image.open(frames/'03.png') as poster:
        poster.convert('RGB').save(output/'poster.jpg', quality=94)
    (output/'frames.ffconcat').write_text('\n'.join(concat)+'\n',encoding='utf-8',newline='\n')
    (output/'workfloor-v041-walkthrough.vtt').write_text('\n'.join(vtt),encoding='utf-8',newline='\n')
    command=[str(ffmpeg),'-hide_banner','-nostdin','-y','-loglevel','error','-f','concat','-safe','0','-i','frames.ffconcat','-r','25','-t','84','-c:v','libx264','-crf','18','-preset','medium','-pix_fmt','yuv420p','-movflags','+faststart','-an','workfloor-v041-walkthrough.mp4']
    subprocess.run(command,cwd=output,check=True,timeout=240)
    # Decode every output frame; this catches corrupt/truncated encoded output.
    subprocess.run([str(ffmpeg),'-hide_banner','-nostdin','-v','error','-i',str(output/'workfloor-v041-walkthrough.mp4'),'-f','null','-'],check=True,timeout=120)
    video=(output/'workfloor-v041-walkthrough.mp4').read_bytes()
    result=dict(schema=1,application_version='0.4.1',source_revision=SOURCE,source_zip_sha256=record['release_zip_sha256'],capture_record_sha256=sha(record_bytes),duration_seconds=84,width=1280,height=900,fps=25,audio=False,
                capture_verification_url='https://github.com/TheOutlandsDev/workfloor/actions/runs/40722383756',
                poster_sha256=sha((output/'poster.jpg').read_bytes()),
                format='Edited step walkthrough from actual Windows CI UI captures; no continuous screen recording; report header and preview table use documented detail crops',
                fixture_note=record['fixture_note'],capture_checks=record['checks'],chapters=chapters,bytes=len(video),sha256=sha(video),captions_sha256=sha((output/'workfloor-v041-walkthrough.vtt').read_bytes()),frames={p.name:sha(p.read_bytes()) for p in sorted(frames.iterdir())},validation=['capture_hashes_match','caption_bounds_fit','six_chapters_cover_84_seconds','complete_video_decode'])
    (output/'video-receipt.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(dict(status='PASS',duration_seconds=84,bytes=len(video),sha256=sha(video))))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('captures','output','ffmpeg','regular-font','bold-font'): parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args(); build(args.captures,args.output,args.ffmpeg,args.regular_font,args.bold_font)
