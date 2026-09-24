"""Synthetic publication tests; exact private engine capture is optional."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
LOADER = importlib.util.spec_from_file_location('pending_startup_patch', HERE / 'patch-browser-pending-startup.py')
patcher = importlib.util.module_from_spec(LOADER)
LOADER.loader.exec_module(patcher)
PRIVATE_SOURCE_DIR = None


def synthetic_spec(path='GameInstance.cpp'):
    old = b'\t\tUE_LOG(LogLoad, Error, TEXT("startup failure"));'
    new = b'#if PLATFORM_HTML5_BROWSER\n\t\tif (BrowseRet != EBrowseReturnVal::Pending)\n#endif\n' + old
    source = b'head\n' + old + b'\nbootstrap();\n'
    output = source.replace(old, new, 1)
    return ({'path': path, 'source_sha256': hashlib.sha256(source).hexdigest(), 'source_bytes': len(source),
             'output_sha256': hashlib.sha256(output).hexdigest(), 'output_bytes': len(output),
             'old': old, 'new': new}, source, output)


class TransformTests(unittest.TestCase):
    def test_exact_transform_inverse_and_modified_inputs_rejected(self):
        spec, source, output = synthetic_spec()
        self.assertEqual(patcher.transform(source, spec), output)
        self.assertEqual(patcher.inverse(output, spec), source)
        self.assertEqual(patcher.transform(output, spec), output)
        for bad in (source + b' ', output + b' ', output.replace(b'Pending', b'Failure')):
            with self.subTest(bad=hashlib.sha256(bad).hexdigest()):
                with self.assertRaises(ValueError):
                    patcher.transform(bad, spec)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'Engine/Build').mkdir(parents=True)
        (self.root / '.tournament-browser-port').write_text('synthetic isolated root')
        (self.root / 'Engine/Build/Build.version').write_text(json.dumps(
            dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        self.spec, self.source_bytes, self.output_bytes = synthetic_spec()
        self.source = self.root / self.spec['path']
        self.source.write_bytes(self.source_bytes)
        self.backup = Path(str(self.source) + patcher.BACKUP)

    def run_patch(self, apply=False):
        return patcher.patch(self.root, apply, self.spec)

    def test_default_readonly_then_apply_backup_and_idempotence(self):
        before = sorted(p.relative_to(self.root) for p in self.root.rglob('*'))
        self.assertFalse(self.run_patch()['apply'])
        self.assertEqual(self.source.read_bytes(), self.source_bytes)
        self.assertEqual(before, sorted(p.relative_to(self.root) for p in self.root.rglob('*')))
        self.run_patch(True)
        self.assertEqual(self.backup.read_bytes(), self.source_bytes)
        self.assertEqual(self.source.read_bytes(), self.output_bytes)
        with mock.patch.object(patcher.os, 'replace', side_effect=AssertionError('unexpected replace')):
            self.assertTrue(self.run_patch(True)['files'][0]['alreadyPatched'])

    def test_already_patched_without_exact_backup_and_wrong_source_rejected(self):
        self.source.write_bytes(self.output_bytes)
        with self.assertRaisesRegex(ValueError, 'requires its exact original backup'):
            self.run_patch(True)
        self.backup.write_bytes(b'wrong backup')
        with self.assertRaisesRegex(ValueError, 'backup differs'):
            self.run_patch(True)
        with self.assertRaises(ValueError):
            patcher.transform(self.source_bytes + b'changed', self.spec)

    def test_drift_after_staging_is_not_overwritten(self):
        original_recheck = patcher.recheck
        seen = 0
        def inject(saved):
            nonlocal seen
            if saved['path'] == self.source:
                seen += 1
                staging = list(self.root.glob('.pending-startup-patch-*'))
                if seen == 4:  # pre-replace recheck, after staged file is flushed
                    self.assertEqual(len(staging), 1)
                    self.source.write_bytes(b'external concurrent edit')
            original_recheck(saved)
        with mock.patch.object(patcher, 'recheck', side_effect=inject):
            with self.assertRaisesRegex(ValueError, 'changed after preflight'):
                self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), b'external concurrent edit')
        self.assertEqual(self.backup.read_bytes(), self.source_bytes)
        self.assertEqual(list(self.root.glob('.pending-startup-patch-*')), [])

    def test_wrong_build_and_hardlinked_source_refused(self):
        (self.root / 'Engine/Build/Build.version').write_text('{}')
        with self.assertRaises(ValueError):
            self.run_patch(True)
        (self.root / 'Engine/Build/Build.version').write_text(json.dumps(
            dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        alias = self.root / 'alias.cpp'
        os.link(self.source, alias)
        with self.assertRaises(ValueError):
            self.run_patch(True)
        self.assertFalse(self.backup.exists())


class PrivateSourceTests(unittest.TestCase):
    def test_exact_private_candidate_and_extracted_controlflow_suite(self):
        if not PRIVATE_SOURCE_DIR:
            self.skipTest('private GameInstance capture not supplied')
        source_dir = Path(PRIVATE_SOURCE_DIR)
        raw = (source_dir / 'GameInstance.cpp').read_bytes()
        candidate_dir = source_dir.parent / 'pending-log-candidate'
        candidate = (candidate_dir / 'GameInstance.cpp.candidate').read_bytes()
        metadata = json.loads((candidate_dir / 'candidate.json').read_text())
        self.assertEqual(hashlib.sha256(raw).hexdigest(), patcher.SPEC['source_sha256'])
        self.assertEqual(hashlib.sha256(candidate).hexdigest(), patcher.SPEC['output_sha256'])
        self.assertEqual(metadata['sourceSHA256'], patcher.SPEC['source_sha256'])
        self.assertEqual(metadata['outputSHA256'], patcher.SPEC['output_sha256'])
        self.assertEqual(patcher.transform(raw), candidate)
        self.assertEqual(patcher.inverse(candidate), raw)
        subprocess.run([sys.executable, '-B', str(candidate_dir / 'test_candidate.py')],
                       check=True, capture_output=True, text=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-source-dir')
    args, remaining = parser.parse_known_args()
    PRIVATE_SOURCE_DIR = args.private_source_dir
    unittest.main(argv=[__file__, *remaining])
