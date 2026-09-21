"""Focused tests for path isolation, allowlists and bounded sparse traversal."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import prepare_cow as cow

_ACTIVE_ROOT = None


def guard_test_file_writes(event, args):
    """Fail before any test file write outside that test's private temp directory."""
    if event != "open" or _ACTIVE_ROOT is None:
        return
    filename, mode, flags = args
    if isinstance(filename, int):
        return
    if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND):
        destination = Path(os.fsdecode(filename)).resolve()
        if not cow.inside(destination, _ACTIVE_ROOT):
            raise AssertionError(f"Test attempted a write outside its temp directory: {destination}")
        if destination.exists() and destination.stat().st_nlink != 1:
            raise AssertionError(f"Test attempted to write a hardlinked file: {destination}")


sys.addaudithook(guard_test_file_writes)


class CowTests(unittest.TestCase):
    def setUp(self):
        global _ACTIVE_ROOT
        # Keep even transient test files inside the owned compatibility directory.
        self.temp = tempfile.TemporaryDirectory(prefix=".test-", dir=Path(__file__).parent)
        self.root = Path(self.temp.name).resolve()
        _ACTIVE_ROOT = self.root

    def tearDown(self):
        global _ACTIVE_ROOT
        try:
            self.temp.cleanup()
        finally:
            _ACTIVE_ROOT = None

    def manifest(self, entries):
        p = self.root / "manifest.json"
        p.write_text(json.dumps({"schema": 1, "meshes": [], "assets": entries}))
        return p

    def test_robot_only_default(self):
        _, packages, new = cow.load_manifest(Path(__file__).parent / "manifest.robot.json")
        self.assertEqual(set(packages), cow.ROBOT_PACKAGES)
        self.assertFalse(new)

    def test_reject_traversal_and_unknown_operation(self):
        for entry in [
            {"package": "/Game/../Outside", "operation": "repair_robot"},
            {"package": "/Game/A", "operation": "replace_everything"},
            {"package": "/Game/A", "operation": "repair_robot"},
        ]:
            with self.subTest(entry=entry), self.assertRaises(cow.Unsafe):
                cow.load_manifest(self.manifest([entry]))

    def test_color_requires_opt_in_and_visible_tint(self):
        entry = {"package": "/Game/A", "operation": "fallback_color_experimental"}
        with self.assertRaises(cow.Unsafe):
            cow.load_manifest(self.manifest([entry]))
        entry.update(experimental=True, tint=[0, 0, 0])
        with self.assertRaises(cow.Unsafe):
            cow.load_manifest(self.manifest([entry]))
        entry["tint"] = [0.5, 0.5, 0.5]
        self.assertEqual(cow.load_manifest(self.manifest([entry]))[1], ["/Game/A"])

    def test_textured_requires_explicit_object_path(self):
        entry = {"package": "/Game/A", "operation": "fallback_textured"}
        with self.assertRaises(cow.Unsafe):
            cow.load_manifest(self.manifest([entry]))
        entry.update(diffuse_texture="/Game/T.T", source_parameter="Diffuse", fallback_parent="/Game/HTML5Compat/M_A")
        _, packages, new = cow.load_manifest(self.manifest([entry]))
        self.assertEqual(len(packages), 2)
        self.assertEqual(new, {"/Game/HTML5Compat/M_A"})

    def test_duplicate_package_and_parent_rejected(self):
        entry = {"package": "/Game/A", "operation": "fallback_textured", "diffuse_texture": "/Game/T.T", "fallback_parent": "/Game/HTML5Compat/M_A"}
        for second in [dict(entry), dict(entry, package="/Game/B")]:
            with self.assertRaises(cow.Unsafe):
                cow.load_manifest(self.manifest([entry, second]))

    def test_sparse_plan_copies_siblings_but_does_not_walk_unselected_tree(self):
        src = self.root / "original"
        (src / "Chosen").mkdir(parents=True)
        (src / "HugeTextures").mkdir()
        (src / "Chosen" / "A.uasset").write_bytes(b"selected")
        (src / "Chosen" / "B.uasset").write_bytes(b"unchanged sibling")
        (src / "HugeTextures" / "unread.bin").write_bytes(b"not copied")
        ops = cow.sparse_plan(src, [Path("Chosen/A.uasset"), Path("HTML5Compat/New.uasset")], src)
        copies = [op["relative"].as_posix() for op in ops if op["kind"] == "copy"]
        self.assertEqual(copies, ["Chosen/A.uasset", "Chosen/B.uasset"])
        self.assertEqual([op["relative"] for op in ops if op["kind"] == "junction"], [Path("HugeTextures")])
        self.assertIn(Path("HTML5Compat"), [op["relative"] for op in ops if op["kind"] == "mkdir"])

    def test_symlink_ancestor_and_hardlink_rejected(self):
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaises(cow.Unsafe):
            cow.physical(alias / "not-created.uasset", allow_missing=True)
        a, b = real / "a", real / "b"
        a.write_bytes(b"a")
        os.link(a, b)
        with self.assertRaises(cow.Unsafe):
            cow.physical(b)

    def test_copy_is_independent_and_never_overwrites(self):
        source, target = self.root / "source", self.root / "private" / "asset"
        source.write_bytes(b"original")
        cow.copy_new(source, target)
        self.assertEqual(target.stat().st_nlink, 1)
        target.write_bytes(b"changed")
        self.assertEqual(source.read_bytes(), b"original")
        with self.assertRaises(cow.Unsafe):
            cow.copy_new(source, target)

    def test_outside_source_junction_rejected(self):
        source, outside = self.root / "original", self.root / "outside"
        source.mkdir(); outside.mkdir()
        (source / "Bad").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(cow.Unsafe):
            cow.sparse_plan(source, [], source)

    def test_audit_detects_source_or_unselected_copy_changes(self):
        src, dst = self.root / "src", self.root / "dst"
        src.write_bytes(b"same"); dst.write_bytes(b"same")
        receipt = self.root / "receipt.json"
        row = {"source": str(src), "file": str(dst), "sha1": cow.sha1(src), "mutable": False}
        receipt.write_text(json.dumps({"copied_content_files": [row], "files": []}))
        with contextlib.redirect_stdout(io.StringIO()):
            cow.audit(receipt)
        dst.write_bytes(b"unexpected")
        with self.assertRaises(cow.Unsafe):
            cow.audit(receipt)
        dst.write_bytes(b"same"); src.write_bytes(b"unexpected")
        with self.assertRaises(cow.Unsafe):
            cow.audit(receipt)

    def test_existing_identical_plugin_is_preserved(self):
        # Entirely synthetic source: this test never traverses the real plugin.
        fixture = self.root / "fixture"
        fixture_plugin = fixture / "UT4Html5Compat"
        fixture_plugin.mkdir(parents=True)
        (fixture_plugin / "UT4Html5Compat.uplugin").write_text('{"FileVersion":3}')
        (fixture_plugin / "Example.cpp").write_text("// synthetic fixture\n")
        installed = self.root / "plugin"
        for fixture_source, fixture_destination in cow.tree_plan(fixture_plugin, installed):
            cow.copy_new(fixture_source, fixture_destination)
        binary = installed / "Binaries" / "Win64" / "example.dll"
        binary.parent.mkdir(parents=True)
        binary.write_bytes(b"matching build output retained")
        with patch.object(cow, "HERE", fixture):
            self.assertTrue(cow.matching_plugin(installed))
            self.assertEqual(binary.read_bytes(), b"matching build output retained")
            (installed / "UT4Html5Compat.uplugin").write_text("different source")
            with self.assertRaises(cow.Unsafe):
                cow.matching_plugin(installed)
        self.assertEqual((fixture_plugin / "Example.cpp").read_text(), "// synthetic fixture\n")

    def test_write_guard_rejects_an_outside_destination(self):
        # A made-up sibling filename, not any real source file; blocked before open.
        forbidden = self.root.parent / (self.root.name + "-must-not-exist")
        with self.assertRaises(AssertionError):
            forbidden.write_bytes(b"blocked")
        self.assertFalse(forbidden.exists())


if __name__ == "__main__":
    unittest.main()
