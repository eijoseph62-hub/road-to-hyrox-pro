"""Read validated FIT sessions; keep only the metrics needed by the coach."""
import hashlib
import json
import math
import os
import tempfile
from datetime import timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
TARGET = {'race': 'HYROX PRO SINGLES', 'date': '2027.03', 'pace': '5:00', 'repeats': 8}


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def load_json(path, default=None):
    return json.loads(Path(path).read_text()) if Path(path).exists() else default


def read_fit(path):
    import fitdecode
    sessions = []
    # CRC errors fail closed. Raw coordinates and record streams are never persisted.
    with fitdecode.FitReader(path, check_crc=fitdecode.CrcCheck.RAISE) as fit:
        for frame in fit:
            if isinstance(frame, fitdecode.FitDataMessage) and frame.name == 'session':
                sessions.append({f.name: f.value for f in frame.fields})
    if len(sessions) != 1 or sessions[0].get('sport') != 'running':
        raise ValueError('単一のランニング記録を含むFITが必要です。')
    s = sessions[0]
    distance, timer = s.get('total_distance'), s.get('total_timer_time')
    if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in (distance, timer)):
        raise ValueError('距離またはタイマー時間が不正です。')
    start = s['start_time']
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    cadence = s.get('avg_running_cadence', s.get('avg_cadence'))
    # FIT running cadence is full cycles/minute; the site displays steps/minute.
    cadence = int(round(2 * cadence)) if cadence is not None else None
    elapsed = s.get('total_elapsed_time')
    return {
        'id': hashlib.sha256(f'{start.isoformat()}|{distance:.2f}|{timer:.3f}'.encode()).hexdigest(),
        'sourceSha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        'startedAt': start.astimezone(JST).isoformat(),
        'date': start.astimezone(JST).strftime('%Y.%m.%d'),
        'distanceM': distance, 'timerSeconds': timer, 'elapsedSeconds': elapsed,
        'paceSecondsPerKm': timer / (distance / 1000),
        'avgHr': s.get('avg_heart_rate'), 'maxHr': s.get('max_heart_rate'),
        'cadence': cadence, 'source': 'FIT with CRC verification',
    }


def pace(seconds):
    total = int(math.floor(seconds + 0.5))
    return f'{total // 60}:{total % 60:02}'


def metrics(run):
    return {'date': run['date'], 'distance': f"{run['distanceM'] / 1000:.2f}",
            'pace': pace(run['paceSecondsPerKm']),
            'avgHr': str(run['avgHr']) if run['avgHr'] is not None else '—',
            'cadence': str(run['cadence']) if run['cadence'] is not None else '—'}


def comparison(run, history):
    previous = sorted((r for r in history if r['id'] != run['id'] and r['startedAt'] < run['startedAt']),
                      key=lambda r: r['startedAt'])
    if not previous:
        return {'previous': None, 'note': '比較できる実測履歴がまだありません。ペースの改善や悪化は判定しません。'}
    last = previous[-1]
    return {'previous': metrics(last),
            'distanceChangeKm': round((run['distanceM'] - last['distanceM']) / 1000, 3),
            'paceChangeSecondsPerKm': round(run['paceSecondsPerKm'] - last['paceSecondsPerKm'], 1),
            'note': '気温・コース・練習目的・CrossFit疲労を未確認のため、走力の改善とは断定しません。'}


def default_analysis(run):
    m = metrics(run)
    return {
        'good': f"{m['distance']}km、平均{m['pace']}/km。走った実績を土台として積めたわ。",
        'bad': '5:00/km × 8へは、ステーション後の1km反復力が課題。今回のランだけでは達成度を断定しないわ。',
        'next': [
            '<b>今週：</b>CrossFitの負荷と脚の疲労を確認。休養または会話できる強度で30〜40分。',
            '<b>次のポイント練習：</b>回復後に1km × 3本。5:20〜5:30/kmを目安に、きつければ落として揃える。',
            '<b>2027年3月へ：</b>回復を優先し、反復を3→4→5→8本へ段階的に。最終目標は5:00/km × 8。',
        ],
    }


def validate(data, run=None):
    expected = {'analysisDate', 'good', 'bad', 'next', 'latestRun', 'target'}
    if set(data) != expected:
        raise ValueError('training-data.jsonのキーが既存スキーマと一致しません。')
    if not all(isinstance(data[k], str) and data[k].strip() for k in ['analysisDate', 'good', 'bad']):
        raise ValueError('日付・GOOD・BADが必要です。')
    if not isinstance(data['next'], list) or len(data['next']) != 3 or not all(isinstance(x, str) and x.strip() for x in data['next']):
        raise ValueError('NEXTは3件必要です。')
    if set(data['latestRun']) != {'date', 'distance', 'pace', 'avgHr', 'cadence'} or not all(isinstance(v, str) for v in data['latestRun'].values()):
        raise ValueError('計測値の形式が不正です。')
    # NEXT uses innerHTML in the production site; only the established <b> label is allowed.
    import re
    for line in data['next']:
        if re.search(r'[<>]', line.replace('<b>', '').replace('</b>', '')):
            raise ValueError('NEXTに許可されていないHTMLが含まれます。')
    if data['target'] != TARGET:
        raise ValueError('レース目標は固定です。')
    if run and (data['latestRun'] != metrics(run) or data['analysisDate'] != run['date']):
        raise ValueError('表示値とFITが一致しません。')
    return data


def prepare(fit_path, history_path, out_path, current_path, analysis_path=None):
    out = Path(out_path)
    if out.exists() and any(out.iterdir()):
        raise ValueError('出力先に既存ファイルがあります。前回の成果物を混同しないよう、新しい出力フォルダを指定してください。')
    run = read_fit(fit_path)
    history = load_json(history_path, [])
    current = load_json(current_path)
    # Keep already-approved wording when exactly the same measured activity is uploaded again.
    if analysis_path:
        analysis = load_json(analysis_path)
    elif current and current.get('latestRun') == metrics(run):
        analysis = {k: current[k] for k in ['good', 'bad', 'next']}
    else:
        analysis = default_analysis(run)
    data = validate({'analysisDate': run['date'], **analysis, 'latestRun': metrics(run), 'target': TARGET}, run)
    out.mkdir(parents=True, exist_ok=True)
    report = {'status': 'prepared-not-published', 'run': run, 'comparison': comparison(run, history),
              'voice': 'approved generic message reused; no new speech or lip sync',
              'reviewRequired': True}
    atomic_json(out / 'training-data.json', data)
    atomic_json(out / 'report.json', report)
    # Only replace the history after validation succeeds; duplicate hashes stay idempotent.
    history = [r for r in history if r['id'] != run['id']] + [run]
    history.sort(key=lambda r: r['startedAt'])
    atomic_json(history_path, history)
    return report
