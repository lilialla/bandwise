"""Synthetic, offline tests. No account calls or learner files are used."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).parents[1] / 'ielts-speaking/scripts/speaking_record.py'
spec = importlib.util.spec_from_file_location('speaking_record', SCRIPT)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def sample():
    return {
        'schema_version': 1, 'record_id': 'sample-first', 'session_id': 'sample-session',
        'date': '2026-09-07', 'mode': 'mock', 'scope': 'full_mock',
        'full_mock_completed': True,
        'question_bank': {'name': 'synthetic practice', 'version': None,
                          'source_url': None, 'status': 'self_authored'},
        'turns': [{'id': f'q{i}', 'part': i, 'question': 'Synthetic prompt',
                   'answer': 'A synthetic learner response.', 'answer_status': 'transcript',
                   'attempt': 'first'} for i in (1, 2, 3)],
        'assessment': {'reviewer': 'ChatGPT Voice', 'model': None, 'basis': 'audio',
                       'audio_observed': True,
                       'scores': {k: {'band': 6.5, 'evidence': 'q1: synthetic observation'}
                                  for k in ('fc', 'lr', 'gra', 'pr')},
                       'priority_fixes': ['Synthetic fix'], 'next_practice': 'Synthetic retry'}
    }


class SpeakingRecordTest(unittest.TestCase):
    def test_audio_scores_remain_external(self):
        result = mod.normalize(sample())
        self.assertEqual(result['overall_estimate'], 6.5)
        self.assertFalse(result['audio_reviewed_locally'])
        self.assertEqual(result['score_source'], 'external_ai_feedback')

    def test_transcript_cannot_support_pronunciation_or_fluency_band(self):
        raw = sample()
        raw['assessment'].update(basis='transcript', audio_observed=False)
        result = mod.normalize(raw)
        self.assertIsNone(result['scores']['pr'])
        self.assertIsNone(result['scores']['fc'])
        self.assertEqual(result['scores']['lr'], 6.5)
        self.assertIsNone(result['overall_estimate'])
        self.assertEqual(raw['assessment']['scores']['pr']['band'], 6.5)

    def test_insufficient_scope_and_assistance_do_not_produce_overall(self):
        for change in ('scope', 'coverage', 'completion', 'assistance', 'reconstruction'):
            with self.subTest(change=change):
                raw = sample()
                if change == 'scope': raw['scope'] = 'single_part'
                if change == 'coverage': raw['turns'] = raw['turns'][:1]
                if change == 'completion': raw['full_mock_completed'] = False
                if change == 'assistance': raw['turns'][0]['attempt'] = 'assisted'
                if change == 'reconstruction': raw['turns'][0]['answer_status'] = 'reconstruction'
                self.assertIsNone(mod.normalize(raw)['overall_estimate'])

    def test_missing_answer_or_evidence_does_not_become_score(self):
        raw = sample()
        for t in raw['turns']: t.update(answer=None, answer_status='missing')
        self.assertTrue(all(v is None for v in mod.normalize(raw)['scores'].values()))
        raw = sample()
        raw['assessment']['scores']['pr']['evidence'] = ''
        self.assertIsNone(mod.normalize(raw)['scores']['pr'])

    def test_invalid_inputs_rejected(self):
        for key, value in [('record_id', '../escape'), ('date', '2026-02-30'),
                           ('schema_version', 2), ('mode', 'unknown')]:
            raw = sample(); raw[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): mod.normalize(raw)
        for band in (True, 10, -1, 6.3, float('nan'), float('inf'), 10**400):
            raw = sample(); raw['assessment']['scores']['fc']['band'] = band
            with self.subTest(band=band), self.assertRaises(ValueError): mod.normalize(raw)
        raw = sample(); raw['turns'][1]['id'] = 'q1'
        with self.assertRaises(ValueError): mod.normalize(raw)

    def test_ancestor_symlink_rejected_for_save_and_status(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'root'; outside = Path(d) / 'outside'
            root.mkdir(); (outside / 'records').mkdir(parents=True)
            (root / 'speaking').symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError): mod.save_record(sample(), root)
            with self.assertRaises(ValueError): mod.summarize(root)
            self.assertEqual(list((outside / 'records').iterdir()), [])

    def test_near_limit_export_can_be_read_after_saving(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'root'
            raw = sample(); raw['extra_note'] = 'x' * 1_998_000
            self.assertLess(len(json.dumps(raw).encode()), mod.MAX_BYTES)
            saved = mod.save_record(raw, root)
            self.assertGreater(Path(saved['path']).stat().st_size, mod.MAX_BYTES)
            self.assertEqual(mod.save_record(raw, root)['action'], 'duplicate')
            self.assertEqual(mod.summarize(root)['session_count'], 1)

    def test_save_duplicate_conflict_and_revision(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'learner'
            raw = sample()
            first = mod.save_record(raw, root)
            p = Path(first['path']); before = p.read_bytes()
            self.assertEqual(first['action'], 'saved')
            self.assertEqual(p.stat().st_mode & 0o777, 0o600)
            self.assertEqual(p.parent.stat().st_mode & 0o777, 0o700)
            second = mod.save_record(copy.deepcopy(raw), root)
            self.assertEqual(second['action'], 'duplicate')
            self.assertEqual(p.read_bytes(), before)
            changed = copy.deepcopy(raw); changed['assessment']['next_practice'] = 'Changed'
            with self.assertRaises(ValueError): mod.save_record(changed, root)
            self.assertEqual(p.read_bytes(), before)
            changed['record_id'] = 'sample-revision'
            mod.save_record(changed, root)
            summary = mod.summarize(root)
            self.assertEqual(summary['session_count'], 1)
            self.assertEqual(summary['record_count'], 2)
            self.assertEqual(summary['sessions'][0]['next_practice'], 'Changed')

    def test_nonexistent_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'absent'
            self.assertEqual(mod.summarize(root)['session_count'], 0)
            self.assertFalse(root.exists())

    def test_cli_preview_save_status_and_error(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'learner'; source = Path(d) / 'input.json'
            source.write_text(json.dumps(sample()))
            base = [sys.executable, '-B', str(SCRIPT), '--root', str(root)]
            result = subprocess.run(base + ['import', str(source)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(root.exists())
            result = subprocess.run(base + ['import', str(source), '--save'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run(base + ['status'], capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout)['session_count'], 1)
            source.write_text('{bad json')
            result = subprocess.run(base + ['import', str(source)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn('Traceback', result.stderr)


if __name__ == '__main__':
    unittest.main()
