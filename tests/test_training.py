import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from sayaka.training import TARGET, comparison, default_analysis, metrics, pace, prepare, validate

RUN = {'id':'activity-1','date':'2026.10.21','startedAt':'2026-10-21T06:02:05+09:00',
       'distanceM':8276.13,'timerSeconds':3413.636,'elapsedSeconds':3447.549,
       'paceSecondsPerKm':3413.636/8.27613,'avgHr':145,'maxHr':159,'cadence':170}


class TrainingTests(unittest.TestCase):
    def test_pace_rounds_at_minute_boundary(self):
        self.assertEqual(pace(359.8),'6:00')
        self.assertEqual(metrics(RUN)['pace'],'6:52')

    def test_duplicate_does_not_grow_history_or_invent_comparison(self):
        with tempfile.TemporaryDirectory() as t, patch('sayaka.training.read_fit',return_value=RUN):
            p = Path(t)
            for i in range(2): prepare('unused.fit',p/'history.json',p/f'bundle-{i}',p/'absent.json')
            self.assertEqual(len(json.loads((p/'history.json').read_text())),1)
            self.assertIsNone(json.loads((p/'bundle-1/report.json').read_text())['comparison']['previous'])

    def test_existing_bundle_cannot_mix_old_and_new_outputs(self):
        with tempfile.TemporaryDirectory() as t, patch('sayaka.training.read_fit',return_value=RUN):
            p=Path(t)
            prepare('unused.fit',p/'history.json',p/'bundle',p/'absent.json')
            with self.assertRaises(ValueError): prepare('unused.fit',p/'history.json',p/'bundle',p/'absent.json')

    def test_missing_measurements_not_invented(self):
        r = {**RUN,'avgHr':None,'cadence':None}
        self.assertEqual(metrics(r)['avgHr'],'—')
        self.assertEqual(metrics(r)['cadence'],'—')

    def test_only_earlier_runs_compared(self):
        older = {**RUN,'id':'old','startedAt':'2026-10-10T06:00:00+09:00','distanceM':6710}
        future = {**RUN,'id':'future','startedAt':'2026-11-01T06:00:00+09:00'}
        self.assertEqual(comparison(RUN,[future,older])['distanceChangeKm'],1.566)

    def test_rejects_html_and_wrong_metrics(self):
        data = {'analysisDate':RUN['date'],**default_analysis(RUN),'latestRun':metrics(RUN),'target':TARGET}
        validate(data,RUN)
        data['next'][0] = '<img src=x onerror=alert(1)>'
        with self.assertRaises(ValueError): validate(data,RUN)
        data['next'][0] = '<b>今週：</b>休む'
        data['latestRun']['distance'] = '10.94'
        with self.assertRaises(ValueError): validate(data,RUN)


if __name__=='__main__': unittest.main()
