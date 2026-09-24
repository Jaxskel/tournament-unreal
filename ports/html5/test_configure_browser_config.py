"""Local temporary-directory checks; never installs into a Windows checkout.

Run: python3 -B ports/html5/test_configure_browser_config.py
"""
import contextlib
import io
import json
from pathlib import Path
import runpy
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
INSTALLER = runpy.run_path(str(HERE / 'configure-browser-config.py'))
# Independent fixture of the previously installed v1 text, not a transformation
# of the current template: an accidental change to migration acceptance fails.
V1 = '''; Tournament browser platform configuration v1
; Merge these sections into the isolated project's Config/HTML5/HTML5Engine.ini.
; The game-engine subclass overrides Engine.GameEngine's inherited driver list.
[/Script/UnrealTournament.UTGameEngine]
-NetDriverDefinitions=(DefName="GameNetDriver",DriverClassName="OnlineSubsystemUtils.IpNetDriver",DriverClassNameFallback="OnlineSubsystemUtils.IpNetDriver")
+NetDriverDefinitions=(DefName="GameNetDriver",DriverClassName="/Script/HTML5Networking.WebSocketNetDriver",DriverClassNameFallback="/Script/HTML5Networking.WebSocketNetDriver")

[/Script/Engine.Engine]
BoneWeightMaterialName=/Engine/EngineMaterials/WorldGridMaterial.WorldGridMaterial

[Engine.StartupPackages]
-Package=/Engine/EngineDebugMaterials/BoneWeightMaterial
'''
PREFIX = '; operator settings\n[/Script/Engine.RendererSettings]\nr.CustomSetting=7\n\n'
ARROW = 'ArrowMaterialName=/Engine/EngineMaterials/WorldGridMaterial.WorldGridMaterial'


class BrowserConfigTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ut4-browser-config-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / '.tournament-browser-port').touch()
        self.version = self.root / 'Engine/Build/Build.version'
        self.version.parent.mkdir(parents=True)
        self.version.write_text(json.dumps(dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        self.path = self.root / 'UnrealTournament/Config/HTML5/HTML5Engine.ini'
        self.path.parent.mkdir(parents=True)
        self.backup = self.path.with_suffix('.ini.before-tournament-browser-config')

    def apply(self):
        with contextlib.redirect_stdout(io.StringIO()):
            INSTALLER['configure'](self.root)

    def snapshot(self):
        return {str(p.relative_to(self.root)): (p.read_bytes(), p.stat().st_mtime_ns)
                for p in self.root.rglob('*') if p.is_file()}

    def refuse(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.apply()
        self.assertEqual(self.snapshot(), before, 'refusal changed content/backup/timestamps')

    def assert_v2(self):
        text = self.path.read_text()
        self.assertEqual(text.count('; Tournament browser platform configuration'), 1)
        self.assertIn('; Tournament browser platform configuration v2\n', text)
        self.assertEqual(text.count(ARROW), 1)
        section = text.split('[/Script/Engine.Engine]\n')[-1].split('\n[')[0]
        self.assertIn(ARROW, section)
        self.assertIn('BoneWeightMaterialName=/Engine/EngineMaterials/WorldGridMaterial.WorldGridMaterial', section)
        self.assertIn('DriverClassName="/Script/HTML5Networking.WebSocketNetDriver"', text)
        self.assertIn('-Package=/Engine/EngineDebugMaterials/BoneWeightMaterial', text)
        self.assertNotIn('DefaultMaterialName=', text)

    def test_fresh_install_without_original_has_no_backup_and_is_idempotent(self):
        self.apply()
        self.assert_v2()
        self.assertFalse(self.backup.exists())
        before = self.snapshot()
        self.apply()
        self.assertEqual(self.snapshot(), before)

    def test_original_bytes_are_backed_up_once_and_repeat_does_not_write(self):
        original = b'\xef\xbb\xbf' + PREFIX.replace('\n', '\r\n').encode()
        self.path.write_bytes(original)
        self.apply()
        self.assert_v2()
        self.assertTrue(self.path.read_text().startswith(PREFIX))
        self.assertEqual(self.backup.read_bytes(), original)
        before = self.snapshot()
        self.apply()
        self.assertEqual(self.snapshot(), before)

    def test_exact_v1_migration_preserves_prefix_and_original_backup(self):
        self.path.write_text(PREFIX + V1)
        # The original backup may differ from subsequently edited operator
        # settings outside the managed block; migration must not replace it.
        original = b'\xef\xbb\xbf; original before v1\r\n'
        self.backup.write_bytes(original)
        before_backup = (self.backup.read_bytes(), self.backup.stat().st_mtime_ns)
        self.apply()
        self.assert_v2()
        self.assertTrue(self.path.read_text().startswith(PREFIX))
        self.assertEqual((self.backup.read_bytes(), self.backup.stat().st_mtime_ns), before_backup)
        before = self.snapshot()
        self.apply()
        self.assertEqual(self.snapshot(), before)

    def test_exact_v1_without_backup_migrates_without_inventing_original(self):
        self.path.write_text('\n\n' + V1)
        self.apply()
        self.assert_v2()
        self.assertFalse(self.backup.exists())

    def test_windows_v1_preserves_crlf_bom_and_operator_prefix_bytes(self):
        prefix = b'\xef\xbb\xbf' + PREFIX.replace('\n', '\r\n').encode()
        self.path.write_bytes(prefix + V1.replace('\n', '\r\n').encode())
        self.backup.write_bytes(b'; original backup\r\n')
        backup = (self.backup.read_bytes(), self.backup.stat().st_mtime_ns)
        self.apply()
        data = self.path.read_bytes()
        self.assertTrue(data.startswith(prefix))
        self.assertIn((ARROW + '\r\n').encode(), data)
        self.assertNotIn(b'\n', data.replace(b'\r\n', b''))
        self.assertEqual((self.backup.read_bytes(), self.backup.stat().st_mtime_ns), backup)
        before = self.snapshot()
        self.apply()
        self.assertEqual(self.snapshot(), before)

    def test_mixed_line_endings_inside_legacy_block_refused(self):
        self.path.write_bytes((PREFIX + V1.replace('\n', '\r\n', 1)).encode())
        self.refuse()

    def test_modified_unknown_duplicate_or_nonterminal_v1_refused(self):
        for block in [V1.replace('WorldGridMaterial', 'CustomMaterial'),
                      V1.replace('configuration v1', 'configuration v3'),
                      V1 + V1, V1 + '; operator edit after block\n',
                      V1.replace('[/Script/Engine.Engine]', '[/Script/Other.Engine]'),
                      V1.rstrip(), V1 + ARROW + '\n']:
            with self.subTest(block=block):
                self.path.write_text(PREFIX + block)
                self.refuse()

    def test_modified_or_duplicate_v2_refused(self):
        self.apply()
        good = self.path.read_text()
        for text in [good.replace(ARROW, 'ArrowMaterialName=/Game/Other.Other'),
                     good + '; appended edit\n', good + good,
                     good.replace('configuration v2', 'configuration v99')]:
            with self.subTest(text=text):
                self.path.write_text(text)
                self.refuse()

    def test_conflicting_backup_or_driver_refused(self):
        self.path.write_text(PREFIX)
        self.backup.write_text('unrelated original')
        self.refuse()
        self.backup.unlink()
        self.path.write_text('[/Script/UnrealTournament.UTGameEngine]\n+NetDriverDefinitions=operator\n')
        self.refuse()

    def test_unmarked_or_wrong_revision_refused(self):
        (self.root / '.tournament-browser-port').unlink()
        self.refuse()
        (self.root / '.tournament-browser-port').touch()
        self.version.write_text(json.dumps(dict(MajorVersion=4, MinorVersion=15, Changelist=3228289)))
        self.refuse()


if __name__ == '__main__':
    unittest.main(verbosity=2)
