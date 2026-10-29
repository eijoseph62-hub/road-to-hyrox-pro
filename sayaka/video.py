"""Replace text in the approved V5.1, preserving natural motion and original voice."""
import hashlib
import json
import re
import subprocess
import zipfile
from pathlib import Path

from .training import atomic_json, load_json


def probe(path):
    return json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)]))


def compact_copy(data):
    m = data['latestRun']
    return {'good': [f"{m['distance']}km、土台を積めたわ。", f"平均{m['pace']}/km・平均心拍{m['avgHr']}", 'まずは継続を評価するわ。'],
            'bad': ['5:00/km × 8へ、反復力が課題。', 'イージー走の速さを追わず、', '回復した日に質を積むこと。'],
            'next': [['休養 または', '30〜40分', '疲労を残さず'],
                     ['5:20〜5:30/km', '3本すべて', '同じペースで'],
                     ['3→4→5→8本', '最終目標', '5:00/km × 8']]}


def render(bundle, assets, copy_path=None):
    from PIL import Image, ImageDraw, ImageFont
    bundle, assets = Path(bundle), Path(assets)
    source = assets / 'approved-v51.mp4'
    font = assets / 'NotoSansCJKjp-Regular.otf'
    manifest = load_json(Path(__file__).parent.parent / 'config/assets-manifest.json')
    for name in ['approved-v51.mp4', 'NotoSansCJKjp-Regular.otf']:
        if hashlib.sha256((assets / name).read_bytes()).hexdigest() != manifest[name]:
            raise ValueError(f'承認済み素材と一致しません: {name}')
    data = load_json(bundle / 'training-data.json')
    copy = load_json(copy_path) if copy_path else compact_copy(data)
    if set(copy) != {'good', 'bad', 'next'} or len(copy['good']) != 3 or len(copy['bad']) != 3 or len(copy['next']) != 3 or any(len(x) != 3 for x in copy['next']):
        raise ValueError('動画用文言はGOOD/BAD各3行、NEXTは3カード各3行です。')
    im = Image.new('RGBA', (1080, 1920))
    d = ImageDraw.Draw(im)

    def text(x, y, value, size=32, width=666):
        face = ImageFont.truetype(str(font), size)
        if not isinstance(value, str) or '\n' in value or d.textlength(value, font=face) > width:
            raise ValueError(f'文字が枠を超えます。文字を小さくせず、短くしてください: {value}')
        d.text((x, y), value, font=face, fill='white', anchor='lt')

    d.rectangle((39, 568, 479, 1015), fill='#030705')
    text(120, 586, 'TODAY’S RUN', 42, 350)
    text(120, 642, data['analysisDate'], 25)
    m = data['latestRun']
    for y, label, value in [(706, 'Distance', m['distance']+' km'), (791, 'Avg. Pace', m['pace']+' /km'),
                            (876, 'Avg. Heart Rate', m['avgHr']+' bpm'), (961, 'Avg. Cadence', m['cadence']+' spm')]:
        text(79, y, label, 25, 215)
        text(295, y-5, value, 40, 181)
    for name, bounds, color, lines in [('good', (369,1102,1057,1267),'#007f3b',[1122,1175,1221]),
                                      ('bad', (369,1309,1057,1473),'#940809',[1329,1381,1427])]:
        d.rectangle(bounds, fill=color)
        for i, y in enumerate(lines):
            text(391, y, copy[name][i], 35 if i == 0 else 32)
    for i, x in enumerate([41,385,731]):
        d.rectangle((x,1695,x+308,1855),fill='#020705')
        for j, y in enumerate([1709,1762,1814]):
            text(x+24,y,copy['next'][i][j],32,274)
    overlay = bundle / 'overlay.png'
    im.save(overlay)
    atomic_json(bundle / 'video-copy.json', copy)
    stem = 'SAYAKA_' + data['analysisDate'].replace('.', '-') + '_V5_1'
    output = bundle / (stem + '.mp4')
    subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(source),'-i',str(overlay),
                    '-filter_complex','[0:v][1:v]overlay=0:0:format=auto[v]',
                    '-map','[v]','-map','0:a:0','-c:v','libx264','-preset','fast','-crf','18',
                    '-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',str(output)],check=True)
    result = verify(output, source)
    # Contact sheet supports the human visual check; it is not claimed as continuous playback.
    frames = []
    duration = float(probe(output)['format']['duration'])
    for i,t in enumerate([0,duration/2,max(0,duration-.16)]):
        p = bundle / f'frame-{i}.jpg'
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(output),'-frames:v','1',str(p)],check=True)
        with Image.open(p) as f:
            frames.append(f.resize((360,640)))
    contact = Image.new('RGB',(1080,640))
    for i,f in enumerate(frames): contact.paste(f,(360*i,0))
    contact.save(bundle / 'contact-sheet.jpg')
    atomic_json(bundle / 'quality.json', result)
    archive = bundle / (stem + '.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
        z.write(output,output.name)
        z.write(bundle/'quality.json','quality.json')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None: raise ValueError('ZIP CRCエラー')
    return {'mp4': str(output), 'zip': str(archive), **result}


def verify(output, source):
    info, original = probe(output), probe(source)
    v = next(s for s in info['streams'] if s['codec_type']=='video')
    a = next(s for s in info['streams'] if s['codec_type']=='audio')
    if (v['codec_name'],v['width'],v['height'],v['pix_fmt']) != ('h264',1080,1920,'yuv420p'):
        raise ValueError('映像形式が不正です。')
    if (a['codec_name'],a['profile']) != ('aac','LC'): raise ValueError('音声形式が不正です。')
    if abs(float(info['format']['duration'])-float(original['format']['duration'])) > .05:
        raise ValueError('元素材の再生時間が変わっています。')
    def audio_hash(p):
        raw = subprocess.check_output(['ffmpeg','-v','error','-i',str(p),'-map','0:a:0','-c:a','copy','-f','adts','-'])
        return hashlib.sha256(raw).hexdigest()
    if audio_hash(output) != audio_hash(source): raise ValueError('承認済み音声が変わっています。')
    raw = Path(output).read_bytes()
    if not 0 < raw.find(b'moov') < raw.find(b'mdat'): raise ValueError('faststart未設定')
    subprocess.run(['ffmpeg','-v','error','-i',str(output),'-f','null','-'],check=True)
    return {'status':'automated-checks-passed','width':1080,'height':1920,
            'duration':float(info['format']['duration']), 'audioUnchanged':True,
            'fullDecode':True,'faststart':True,'visualReviewRequired':True,
            'continuousAudiovisualReview':False,'newSpeechGenerated':False}
