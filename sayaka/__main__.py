import argparse
import hashlib
import json
import zipfile
from pathlib import Path
from .training import prepare, validate, load_json, atomic_json


def main():
    p = argparse.ArgumentParser(description='SAYAKA: FIT解析→履歴→動画→検証→公開前レビュー')
    sub = p.add_subparsers(dest='command', required=True)
    a = sub.add_parser('prepare')
    a.add_argument('fit')
    a.add_argument('--history',default='private/history.json')
    a.add_argument('--out',required=True)
    a.add_argument('--current',default='training-data.json')
    a.add_argument('--analysis',help='GOOD/BAD/NEXTを含むJSON。省略時は検証済み既存文言または保守的な初期案。')
    a.add_argument('--assets',help='承認済みMP4と日本語フォントがある非公開フォルダ。指定すると動画まで実行。')
    a.add_argument('--video-copy',help='短い動画用文言のJSON。省略時は固定の保守的な案。')
    a = sub.add_parser('apply')
    a.add_argument('bundle')
    a.add_argument('--approved',action='store_true')
    a.add_argument('--target',default='training-data.json')
    a = sub.add_parser('serve')
    a.add_argument('--port',type=int,default=8787)
    a = sub.add_parser('checkpoint')
    a.add_argument('--history',default='private/history.json')
    a.add_argument('--assets',required=True)
    a.add_argument('--out',required=True)
    args = p.parse_args()
    if args.command == 'prepare':
        result = prepare(args.fit,args.history,args.out,args.current,args.analysis)
        if args.assets:
            from .video import render
            result['video'] = render(args.out,args.assets,args.video_copy)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    elif args.command == 'apply':
        if not args.approved: p.error('公開前のユーザー承認後に --approved を指定してください。')
        root = Path(args.bundle)
        report = load_json(root/'report.json')
        data = validate(load_json(root/'training-data.json'),report['run'])
        atomic_json(args.target,data)
        print('承認済みデータをローカルに反映しました。GitHub公開・配信確認は別途必要です。')
    elif args.command == 'checkpoint':
        # Persist repeatable private state separately from the public Git repository.
        out = Path(args.out)
        out.parent.mkdir(parents=True,exist_ok=True)
        allowed = {'id','sourceSha256','startedAt','date','distanceM','timerSeconds','elapsedSeconds',
                   'paceSecondsPerKm','avgHr','maxHr','cadence','source'}
        history = [{k:v for k,v in r.items() if k in allowed} for r in load_json(args.history,[])]
        assets = Path(args.assets)
        manifest_path = Path(__file__).parent.parent/'config/assets-manifest.json'
        manifest = load_json(manifest_path)
        for name, digest in manifest.items():
            if hashlib.sha256((assets/name).read_bytes()).hexdigest() != digest:
                p.error('承認済み素材と一致しません: '+name)
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            z.writestr('private/history.json',json.dumps(history,ensure_ascii=False,indent=2))
            z.write(manifest_path,'config/assets-manifest.json')
            for name in manifest: z.write(assets/name,'assets-private/'+name)
            if (assets/'FONT-LICENSE.txt').exists(): z.write(assets/'FONT-LICENSE.txt','assets-private/FONT-LICENSE.txt')
            z.writestr('README.txt','非公開のSAYAKA継続用データ。公開GitHubへ追加しないでください。\n次の会話にこのZIPを添付すると、実測履歴と承認済み素材を引き継げます。\nコードはGitHubのSAYAKA開発ブランチを参照。音声の新規合成は未実装。\n')
        with zipfile.ZipFile(out) as z:
            if z.testzip() is not None: raise ValueError('チェックポイントのZIP検証に失敗しました。')
        print('非公開チェックポイントを作成・検証しました: '+str(out))
    else:
        from .server import serve
        serve(args.port)


if __name__ == '__main__': main()
