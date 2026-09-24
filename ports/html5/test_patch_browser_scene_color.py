"""Synthetic publication tests; licensed/private engine captures are optional."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
LOADER = importlib.util.spec_from_file_location('scene_color_patch', HERE / 'patch-browser-scene-color.py')
patcher = importlib.util.module_from_spec(LOADER)
LOADER.loader.exec_module(patcher)
PRIVATE_SOURCE_DIR = None
PRIVATE_MAP = {
    patcher.SPECS[0]['path']: 'visual-parity-source/HLSLMaterialTranslator.h',
    patcher.SPECS[1]['path']: 'visual-parity-source/MobileTranslucentRendering.cpp',
    patcher.SPECS[2]['path']: 'scene-color-feasibility/native-source/TranslucentRendering.cpp',
    patcher.SPECS[3]['path']: 'scene-color-feasibility/native-source/ShaderBaseClasses.cpp',
}


def synthetic_spec(path='sample.cpp'):
    original = b'head\nanchor\nbody\n'
    updated = b'head\nanchor\ninserted\nbody\n'
    return ({'path': path, 'source_sha256': hashlib.sha256(original).hexdigest(), 'source_bytes': len(original),
             'output_sha256': hashlib.sha256(updated).hexdigest(), 'output_bytes': len(updated),
             'edits': (('anchor\n', 'anchor\ninserted\n'),)}, original, updated)


class TransformTests(unittest.TestCase):
    def test_fixed_four_targets_and_exact_pins(self):
        self.assertEqual(len(patcher.SPECS), 4)
        self.assertEqual([s['output_sha256'] for s in patcher.SPECS], [
            'd2346724dc2e8a06290702fa9f1e15d1a16bc80503e3ec2df18885bb5d06314f',
            '7bbed83fc236407c5d1bcea79f1ea4d1aff50a6f857dd6bb597c8019587e4e84',
            'd90d0367a7c25ef18ebb183afdd59a05bc849ea7f79ef947a95df401fbd73d08',
            '76fbb81b8b1e9bc5c43676f197d59c0b4f7284c65e7fc46ab3608f6e62c86831'])
        self.assertEqual(patcher.BACKUP, '.before-tournament-browser-scene-color')

    def test_synthetic_exact_transform_inverse_and_drift_rejection(self):
        spec, original, updated = synthetic_spec()
        self.assertEqual(patcher.transform(original, spec), updated)
        self.assertEqual(patcher.inverse(updated, spec), original)
        self.assertEqual(patcher.transform(updated, spec), updated)
        for bad in (original + b' ', updated + b' ', updated.replace(b'inserted', b'changed')):
            with self.subTest(value=bad):
                with self.assertRaises(ValueError):
                    patcher.transform(bad, spec)
        with self.assertRaises(ValueError):
            patcher.inverse(original, spec)

    def test_crlf_transform_roundtrips_without_normalizing(self):
        spec, original, _ = synthetic_spec()
        original = original.replace(b'\n', b'\r\n')
        updated = original.replace(b'anchor\r\n', b'anchor\r\ninserted\r\n')
        spec.update(source_sha256=hashlib.sha256(original).hexdigest(), source_bytes=len(original),
                    output_sha256=hashlib.sha256(updated).hexdigest(), output_bytes=len(updated))
        spec['edits'] = (('anchor\n', 'anchor\ninserted\n'),)
        self.assertEqual(patcher.transform(original, spec), updated)
        self.assertEqual(patcher.inverse(updated, spec), original)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        (self.root / 'Engine/Build').mkdir(parents=True)
        (self.root / '.tournament-browser-port').write_text('disposable test root')
        (self.root / 'Engine/Build/Build.version').write_text(json.dumps(
            dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        self.spec, self.original, self.updated = synthetic_spec()
        self.source = self.root / self.spec['path']
        self.source.write_bytes(self.original)
        self.backup = Path(str(self.source) + patcher.BACKUP)

    def run_patch(self, apply=False):
        return patcher.patch(self.root, apply, (self.spec,))

    def test_default_is_readonly_then_apply_requires_backup_and_is_idempotent(self):
        before = sorted(p.relative_to(self.root) for p in self.root.rglob('*'))
        report = self.run_patch()
        self.assertFalse(report['apply'])
        self.assertFalse(report['files'][0]['alreadyPatched'])
        self.assertEqual(self.original, self.source.read_bytes())
        self.assertEqual(before, sorted(p.relative_to(self.root) for p in self.root.rglob('*')))
        self.run_patch(True)
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.assertEqual(self.source.read_bytes(), self.updated)
        with mock.patch.object(patcher.os, 'replace', side_effect=AssertionError('unexpected rewrite')):
            self.assertTrue(self.run_patch(True)['files'][0]['alreadyPatched'])

    def test_already_patched_without_backup_and_wrong_backup_refused(self):
        self.source.write_bytes(self.updated)
        with self.assertRaisesRegex(ValueError, 'requires its exact original backup'):
            self.run_patch(True)
        self.assertEqual(self.updated, self.source.read_bytes())
        self.backup.write_bytes(b'wrong original')
        with self.assertRaisesRegex(ValueError, 'backup differs'):
            self.run_patch(True)

    def test_all_files_preflight_before_any_backup_or_source_write(self):
        specs = []
        originals = []
        for index in range(4):
            spec, original, _ = synthetic_spec('src%d.cpp' % index)
            specs.append(spec)
            originals.append(original)
            path = self.root / spec['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(original)
        (self.root / specs[3]['path']).write_bytes(b'drift in final target')
        with self.assertRaises(ValueError):
            patcher.patch(self.root, True, tuple(specs))
        for spec, original in zip(specs[:3], originals[:3]):
            source = self.root / spec['path']
            self.assertEqual(source.read_bytes(), original)
            self.assertFalse(Path(str(source) + patcher.BACKUP).exists())

    def test_wrong_version_and_hardlinked_source_refused(self):
        (self.root / 'Engine/Build/Build.version').write_text('{}')
        with self.assertRaises(ValueError):
            self.run_patch(True)
        (self.root / 'Engine/Build/Build.version').write_text(json.dumps(
            dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        alias = self.root / 'source-alias'
        os.link(self.source, alias)
        with self.assertRaises(ValueError):
            self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertFalse(self.backup.exists())

    def test_backup_and_install_failure_leave_original_and_evidence(self):
        original_replace = patcher.os.replace
        def fail_install(src, dst):
            self.assertEqual(self.backup.read_bytes(), self.original)
            self.assertEqual(Path(src).read_bytes(), self.updated)
            raise OSError('injected install failure')
        with mock.patch.object(patcher.os, 'replace', side_effect=fail_install):
            with self.assertRaises(OSError):
                self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), self.original)
        self.assertEqual(self.backup.read_bytes(), self.original)
        with mock.patch.object(patcher.os, 'replace', original_replace):
            self.run_patch(True)

    def test_four_backups_precede_first_replace_and_midway_failure_recovers(self):
        specs = []
        originals = []
        updated = []
        backups = []
        for index in range(4):
            spec, raw, fixed = synthetic_spec('multi%d.cpp' % index)
            specs.append(spec)
            originals.append(raw)
            updated.append(fixed)
            source = self.root / spec['path']
            source.write_bytes(raw)
            backups.append(Path(str(source) + patcher.BACKUP))

        real_replace = patcher.os.replace
        replacements = 0
        def fail_second(src, dst):
            nonlocal replacements
            self.assertEqual([p.read_bytes() for p in backups], originals)
            replacements += 1
            if replacements == 2:
                raise OSError('injected second-source failure')
            return real_replace(src, dst)

        with mock.patch.object(patcher.os, 'replace', side_effect=fail_second):
            with self.assertRaisesRegex(OSError, 'second-source'):
                patcher.patch(self.root, True, tuple(specs))
        self.assertEqual([p.read_bytes() for p in backups], originals)
        self.assertEqual([(self.root / s['path']).read_bytes() for s in specs],
                         [updated[0], *originals[1:]])

        patcher.patch(self.root, True, tuple(specs))
        self.assertEqual([p.read_bytes() for p in backups], originals)
        self.assertEqual([(self.root / s['path']).read_bytes() for s in specs], updated)

    def test_source_drift_after_staging_aborts_without_overwrite(self):
        original_recheck = patcher.recheck
        seen = 0
        def inject_after_stage(saved):
            nonlocal seen
            if saved['path'] == self.source:
                seen += 1
                staging = list(self.root.glob('.scene-color-patch-*'))
                # One initial check, one backup-publication check, one barrier
                # check, then the pre-replace check after the patch temp is flushed.
                if seen == 4:
                    self.assertEqual(len(staging), 1)
                    self.source.write_bytes(b'concurrent source drift')
            original_recheck(saved)

        with mock.patch.object(patcher, 'recheck', side_effect=inject_after_stage):
            with self.assertRaisesRegex(ValueError, 'changed after preflight'):
                self.run_patch(True)
        self.assertEqual(self.source.read_bytes(), b'concurrent source drift')
        self.assertEqual(self.backup.read_bytes(), self.original)
        self.assertEqual(list(self.root.glob('.scene-color-patch-*')), [])


class PrivatePinnedSources(unittest.TestCase):
    def test_private_four_originals_transform_to_receipt_outputs(self):
        if not PRIVATE_SOURCE_DIR:
            self.skipTest('private source captures not supplied; exact public pins remain covered synthetically')
        root = Path(PRIVATE_SOURCE_DIR)
        receipt_path = root / 'scene-color-feasibility/candidate/output-2/receipt.json'
        receipt = json.loads(receipt_path.read_text())
        rows = {row['target']: row for row in receipt['files']}
        output_root = receipt_path.parent
        for spec in patcher.SPECS:
            with self.subTest(path=spec['path']):
                raw = (root / PRIVATE_MAP[spec['path']]).read_bytes()
                desired = (output_root / spec['path']).read_bytes()
                self.assertEqual(len(raw), spec['source_bytes'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), spec['source_sha256'])
                self.assertEqual(len(desired), spec['output_bytes'])
                self.assertEqual(hashlib.sha256(desired).hexdigest(), spec['output_sha256'])
                self.assertEqual(patcher.transform(raw, spec), desired)
                self.assertEqual(patcher.inverse(desired, spec), raw)
                self.assertEqual(rows[spec['path']]['sourceSha256'], spec['source_sha256'])
                self.assertEqual(rows[spec['path']]['outputSha256'], spec['output_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-source-dir')
    args, remaining = parser.parse_known_args()
    PRIVATE_SOURCE_DIR = args.private_source_dir
    unittest.main(argv=[__file__, *remaining])
