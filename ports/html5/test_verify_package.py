"""Exercise archive corruption detection without licensed engine/content files."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('verify_package', Path(__file__).with_name('verify-package.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackageVerification(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / 'stage'
        self.stage.mkdir()
        (self.stage / 'game.pak').write_bytes(b'package fixture')
        (self.stage / 'config.ini').write_bytes(b'config fixture')
        self.archive = self.root / 'game.data'
        self.archive.write_bytes(b'package fixtureconfig fixture')
        self.loader = self.root / 'game.data.js'
        self.metadata = {'remote_package_size': 29, 'files': [
            {'filename': '/game.pak', 'start': 0, 'end': 15},
            {'filename': '/config.ini', 'start': 15, 'end': 29},
        ]}

    def verify(self):
        self.loader.write_text('loadPackage(' + json.dumps(self.metadata) + ');\n')
        return module.verify(self.loader, self.archive, self.stage)

    def test_complete_archive_and_staged_bytes_match(self):
        result = self.verify()
        self.assertTrue(result['sliceComparisonsPassed'])
        self.assertEqual(result['bytes'], 29)
        self.assertEqual(len(result['entries']), 2)

    def test_same_size_corruption_is_rejected(self):
        self.archive.write_bytes(b'X' + self.archive.read_bytes()[1:])
        with self.assertRaisesRegex(ValueError, 'bytes differ'):
            self.verify()

    def test_truncated_archive_is_rejected(self):
        self.archive.write_bytes(self.archive.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, 'size does not match'):
            self.verify()

    def test_missing_stage_file_is_rejected(self):
        (self.stage / 'config.ini').unlink()
        with self.assertRaisesRegex(ValueError, 'absent or size differs'):
            self.verify()

    def test_outside_stage_file_is_rejected(self):
        outside = self.root / 'outside'
        outside.write_bytes(b'package fixture')
        (self.stage / 'game.pak').unlink()
        (self.stage / 'game.pak').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'absent or size differs'):
            self.verify()

    def test_invalid_metadata_paths_and_ranges_are_rejected(self):
        original = json.dumps(self.metadata)
        changes = [('filename', '/../game.pak'), ('filename', 'game.pak'),
                   ('filename', '/folder\\game.pak'), ('filename', '/config.ini'),
                   ('start', 1), ('end', 30), ('end', True), ('crunched', True)]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.metadata = json.loads(original)
                self.metadata['files'][0][key] = value
                with self.assertRaises(ValueError):
                    self.verify()

    def test_trailing_unmapped_bytes_are_rejected(self):
        self.metadata['files'].pop()
        with self.assertRaisesRegex(ValueError, 'complete archive'):
            self.verify()


if __name__ == '__main__':
    unittest.main()
