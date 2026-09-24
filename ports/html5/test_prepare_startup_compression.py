"""Synthetic response-only tests; no engine, cook, UnrealPak or asset payloads.

Optional: --private-response=/path/to/pinned/paklist.txt checks the actual 9173-row
input against the reviewed output hash, entirely in memory. Never bundled here.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location('startup_compression', Path(__file__).with_name('prepare-startup-compression.py'))
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)
PRIVATE_RESPONSE = None


def row(name, flags=b' -compress', source=None, ending=b'\r\n'):
    source = source or ('C:/Synthetic Cook/' + name)
    return b'"' + source.encode() + b'" "../../../' + name.encode() + b'"' + flags + ending


def fixture(ending=b'\r\n', bom=True):
    return (P.BOM if bom else b'') + b''.join(row(n, ending=ending) for n in P.SELECTED) + row('Other/Keep.uasset', ending=ending)


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.input = self.root / 'input.txt'
        self.input.write_bytes(fixture())

    def cli(self, *extra, pin=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        args = ['--input', str(self.input), '--input-sha256', pin or P.sha256(self.input.read_bytes()), *map(str, extra)]
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = P.main(args)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_only_twelve_compression_spans_removed(self):
        raw = fixture()
        output, removals, count = P.transform(raw)
        expected = P.BOM + b''.join(row(n, flags=b'') for n in P.SELECTED) + row('Other/Keep.uasset')
        self.assertEqual(output, expected)
        self.assertEqual(count, 13)
        self.assertEqual(len(raw)-len(output), 120)
        self.assertEqual(P.inverse(output, removals), raw)

    def test_bom_mixed_newlines_whitespace_and_unterminated_last_row(self):
        rows = [b'  ' + row(n, flags=b'\t\t-compress \t-encrypt  ', ending=b'\n' if i % 2 else b'\r\n')
                for i, n in enumerate(P.SELECTED)]
        raw = P.BOM + b' \t\r\n' + b''.join(rows) + row('Other/Keep.uasset', ending=b'')
        output, removals, _ = P.transform(raw)
        expected = P.BOM + b' \t\r\n' + b''.join(r.replace(b'\t-compress', b'', 1) for r in rows) + row('Other/Keep.uasset', ending=b'')
        self.assertEqual(output, expected)
        self.assertEqual(P.inverse(output, removals), raw)
        self.assertEqual(P.transform(fixture(ending=b'\n', bom=False))[0].count(b'\r'), 0)

    def test_missing_selected_is_not_silently_skipped(self):
        with self.assertRaisesRegex(ValueError, 'Missing selected'):
            P.transform(fixture().replace(row(P.SELECTED[0]), b''))

    def test_selected_already_plain_and_duplicate_flags_rejected(self):
        for flags in [b'', b' -encrypt', b' -compress -compress', b' -compress -encrypt -encrypt']:
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                P.transform(fixture().replace(row(P.SELECTED[0]), row(P.SELECTED[0], flags=flags)))

    def test_duplicate_sources_and_destinations_case_insensitive(self):
        raw = fixture()
        for extra in [row(P.SELECTED[0]),
                      row(P.SELECTED[0].upper(), source='D:/Other/' + P.SELECTED[0].upper()),
                      row('Elsewhere/Keep.uasset', source='c:/synthetic cook/other/Keep.uasset')]:
            with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, 'duplicate'):
                P.transform(raw + extra)

    def test_unknown_and_malformed_flags_rejected_on_unselected_rows(self):
        for flags in [b' -unknown', b' -Compress', b' -compress=1', b' -compress;echo', b' -compress -compress']:
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                P.transform(fixture()+row('Other/Extra.uasset', flags=flags))

    def test_quoted_canonical_paths_required(self):
        bad_rows = [
            b'C:/Cook/a "../../../Other/a" -compress\n',
            row('../escape.uasset'), row('/absolute.uasset'), row('Other//empty.uasset'),
            row('Other/NUL.uasset'), row('Other/file:stream.uasset'), row('Other/wild*.uasset'),
            row('Other/a.uasset', source='relative/a.uasset'),
            row('Other/a.uasset', source='C:/Cook/../a.uasset'),
            row('Other/a.uasset', source='//server/share/a.uasset'),
            row('Other/a.uasset', source='C:/Cook/alias./a.uasset'),
            row('Other/a.uasset', source='C:/Cook/wrong.uasset'),
            row('Other/a.uasset', source='C:/Cook/a\x00.uasset'),
            row('Other/a.uasset').replace(b'Other/a', b'Other\\a'),
        ]
        for bad in bad_rows:
            with self.subTest(row=bad), self.assertRaises(ValueError):
                P.transform(fixture()+bad)

    def test_bounds_encoding_and_bare_cr(self):
        for raw in [b'', b'\xff\xfe'+fixture(), fixture()+b'\xff', fixture().replace(b'\r\n', b'\r'),
                    fixture()+b' '*(P.MAX_LINE_BYTES+1), fixture()+row('Other/'+('a'*P.MAX_PATH_BYTES))]:
            with self.subTest(size=len(raw)), self.assertRaises(ValueError):
                P.transform(raw)
        with mock.patch.object(P, 'MAX_BYTES', 10), self.assertRaisesRegex(ValueError, 'byte limit'):
            P.transform(fixture())
        with mock.patch.object(P, 'MAX_ENTRIES', 12), self.assertRaisesRegex(ValueError, 'Entry count'):
            P.transform(fixture())

    def test_default_is_read_only_plan(self):
        before = self.input.read_bytes()
        code, stdout, stderr = self.cli()
        self.assertEqual((code, stderr), (0, ''))
        result = json.loads(stdout)
        self.assertEqual(result['status'], 'response-only-plan')
        self.assertIsNone(result['output'])
        self.assertEqual(result['input_sha256'], P.sha256(before))
        self.assertEqual(result['output_sha256'], P.sha256(P.transform(before)[0]))
        self.assertEqual(result['selected'], list(P.SELECTED))
        self.assertFalse(result['archive_equivalence_verified'])
        self.assertIn('global -compress', result['warning'])
        self.assertEqual(list(self.root.iterdir()), [self.input])
        self.assertEqual(self.input.read_bytes(), before)

    def test_output_is_exclusive_and_does_not_modify_input(self):
        before = self.input.read_bytes()
        out = self.root/'prepared.txt'
        code, stdout, stderr = self.cli('--output', out)
        self.assertEqual((code, stderr), (0, ''))
        self.assertEqual(json.loads(stdout)['status'], 'response-only-written')
        self.assertEqual(out.read_bytes(), P.transform(before)[0])
        self.assertEqual(self.input.read_bytes(), before)
        for target in [out, self.input]:
            code, stdout, _ = self.cli('--output', target)
            self.assertEqual((code, stdout), (1, ''))
        self.assertEqual(out.read_bytes(), P.transform(before)[0])
        self.assertEqual(self.input.read_bytes(), before)

    def test_output_symlink_collision_refused(self):
        link = self.root/'link.txt'
        try:
            link.symlink_to(self.input)
        except (OSError, NotImplementedError):
            self.skipTest('Symlinks unavailable on this host')
        before = self.input.read_bytes()
        code, stdout, _ = self.cli('--output', link)
        self.assertEqual((code, stdout), (1, ''))
        self.assertEqual(self.input.read_bytes(), before)

    def test_bad_pin_or_format_creates_no_output(self):
        out = self.root/'prepared.txt'
        for pin in ['bad', '0'*64]:
            code, stdout, _ = self.cli('--output', out, pin=pin)
            self.assertEqual((code, stdout), (1, ''))
            self.assertFalse(out.exists())
        self.input.write_bytes(fixture().replace(row(P.SELECTED[0]), b''))
        self.assertEqual(self.cli('--output', out)[0], 1)
        self.assertFalse(out.exists())

    def test_input_drift_and_missing_output_parent_fail_without_writes(self):
        out = self.root/'prepared.txt'
        raw = self.input.read_bytes()
        with mock.patch.object(P, 'read_response', side_effect=[raw, raw+b'\n']):
            self.assertEqual(self.cli('--output', out)[0], 1)
        self.assertFalse(out.exists())
        missing = self.root/'missing'
        self.assertEqual(self.cli('--output', missing/'prepared.txt')[0], 1)
        self.assertFalse(missing.exists())

    def test_private_actual_response_reproduces_reviewed_bytes(self):
        if not PRIVATE_RESPONSE:
            self.skipTest('optional --private-response pinned actual response')
        path = Path(PRIVATE_RESPONSE)
        self.assertFalse(getattr(path.stat(), 'st_flags', 0) & 0x40000000, 'Private response is not resident')
        raw = P.read_response(path)
        self.assertEqual(P.sha256(raw), 'd59ff9ea7f05bf14ca18df26b98d55e98d56fbba03fe8f0b47ad4c0814b80cf8')
        output, removals, entries = P.transform(raw)
        self.assertEqual(entries, 9173)
        self.assertEqual(P.sha256(output), 'f2cd2c85d0598bbe5a1265b5f04ac6837fee00f83912c297d1ab4a5108aecc8a')
        self.assertEqual(P.inverse(output, removals), raw)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--private-response')
    args, remaining = parser.parse_known_args()
    PRIVATE_RESPONSE = args.private_response
    unittest.main(argv=[sys.argv[0], *remaining])
