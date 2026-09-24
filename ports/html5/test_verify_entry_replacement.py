"""Synthetic pak fixtures only; no engine/tool execution or real asset scans."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

V = load('entry_replacement', HERE/'verify-entry-replacement.py')
PUBLIC = HERE/'selective-startup-pak.py'
F = load('pak_fixture', PUBLIC.with_name('test_selective_startup_pak.py'))
P = V.load_parser(PUBLIC)
sha = lambda raw: hashlib.sha256(raw).hexdigest()

class Replacement(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.old = [(V.ENTRY, b'old'*40, False), ('Keep/Z', b'z'*128, True), ('Keep/P', b'p', False)]
        self.new = [(V.ENTRY, b'new'*70, False), *self.old[1:]]
        self.counter = 0

    def pin(self, raw):
        self.counter += 1
        path = self.root/str(self.counter)
        path.write_bytes(raw)
        pin = P.PinnedFile(path, sha(raw))
        self.addCleanup(pin.close)
        return pin

    def archive(self, rows):
        return P.Archive(self.pin(F.pak(rows)))

    def check(self, old=None, new=None, cooked=None):
        return V.verify(self.archive(self.old if old is None else old),
                        self.archive(self.new if new is None else new),
                        self.pin(self.new[0][1] if cooked is None else cooked))

    def test_success_plain_and_compressed_entry_growth_and_shrink(self):
        for compressed in (False, True):
            for raw in (b'changed', b'changed'*100):
                old = [(V.ENTRY, b'old'*40, compressed), *self.old[1:]]
                new = [(V.ENTRY, raw, compressed), *self.old[1:]]
                result = self.check(old, new, raw)
                self.assertEqual(result['unchanged_entries'], 2)
                self.assertFalse(result['whole_map_acceptance'])
                self.assertFalse(result['visual_success'])
                self.assertEqual(result['replacement']['new_decoded_sha256'], sha(raw))

    def test_missing_extra_reordered_and_unchanged_entry(self):
        cases = [(self.old[1:], self.new[1:]), (self.old, self.new+[('Extra',b'x',False)]),
                 (self.old, list(reversed(self.new))), (self.old, self.old)]
        for old, new in cases:
            with self.subTest(new=new), self.assertRaises(ValueError):
                self.check(old, new, new[0][1])
        with self.assertRaisesRegex(ValueError, 'pinned cooked'):
            self.check(cooked=b'wrong')

    def test_other_bytes_methods_and_framing(self):
        for row in [('Keep/Z', b'X'*128, True), ('Keep/Z', b'z'*128, False)]:
            with self.assertRaises(ValueError):
                self.check(new=[self.new[0], row, self.new[2]])
        old, new = self.archive(self.old), self.archive(self.new)
        new.entries[-1]['blocksize'] = 1
        with self.assertRaisesRegex(ValueError, 'framing'):
            V.verify(old, new, self.pin(self.new[0][1]))
        with self.assertRaisesRegex(ValueError, 'Compression'):
            self.check(new=[(V.ENTRY,self.new[0][1],True),*self.new[1:]])

    def test_all_unchanged_compressed_entries_really_decode(self):
        # Valid stored checksums/equal payloads still cannot hide invalid zlib.
        with patch('zlib.compress', return_value=b'invalid-zlib'):
            old, new = self.archive(self.old), self.archive(self.new)
        import zlib
        with self.assertRaises((ValueError, zlib.error)):
            V.verify(old, new, self.pin(self.new[0][1]))

    def cli(self, count=3):
        extra = [(f'Keep/{i}',b'x',False) for i in range(count-3)]
        old, new, cooked = self.pin(F.pak(self.old+extra)), self.pin(F.pak(self.new+extra)), self.pin(self.new[0][1])
        args = ['--parser', str(PUBLIC)]
        for name, pin in zip(('baseline','candidate','cooked-entry'), (old,new,cooked)):
            args += ['--'+name, str(pin.path), '--'+name+'-sha256', pin.expected]
        return args, cooked.path

    def invoke(self, args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = V.main(args)
        return code, out.getvalue(), err.getvalue()

    def test_cli_exact_count_success_readonly_and_qualified_output(self):
        args, _ = self.cli()
        self.assertEqual(self.invoke(args)[:2], (1,''))
        args, _ = self.cli(9179)
        before = {p.name: (sha(p.read_bytes()),p.stat().st_mtime_ns) for p in self.root.iterdir()}
        code, out, err = self.invoke(args)
        self.assertEqual((code,err),(0,''))
        result = json.loads(out)
        self.assertEqual(result['unchanged_entries'],9178)
        self.assertTrue(result['inputs_unchanged'])
        self.assertEqual(before,{p.name:(sha(p.read_bytes()),p.stat().st_mtime_ns) for p in self.root.iterdir()})

    def test_cli_wrong_pins_parser_and_budget(self):
        args, _ = self.cli()
        bad = args[:];bad[bad.index('--cooked-entry-sha256')+1]='0'*64
        self.assertEqual(self.invoke(bad)[:2],(1,''))
        fake = self.root/'parser';fake.write_bytes(b'raise RuntimeError("must not execute")')
        self.assertEqual(self.invoke(args+['--parser',str(fake)])[:2],(1,''))
        with patch.object(V,'MAX_BYTES',1):
            self.assertEqual(self.invoke(args)[:2],(1,''))

    def test_final_rehash_rejects_input_drift(self):
        args, cooked = self.cli(9179)
        real = V.verify
        def drift(*values):
            result = real(*values)
            with cooked.open('ab') as f:
                f.write(b'!')
            return result
        with patch.object(V,'verify',side_effect=drift):
            code, out, err = self.invoke(args)
        self.assertEqual((code,out),(1,''))
        self.assertIn('identity changed',err)

    def test_parser_rejects_mount_duplicate_and_corrupt_payload(self):
        for raw in (F.pak(self.old,mount='Other/'), F.pak([self.old[0],self.old[0]])):
            with self.assertRaises(ValueError):
                P.Archive(self.pin(raw))
        raw = bytearray(F.pak(self.new));raw[53] ^= 1
        with self.assertRaisesRegex(ValueError,'payload checksum'):
            V.verify(self.archive(self.old),P.Archive(self.pin(bytes(raw))),self.pin(self.new[0][1]))

if __name__ == '__main__':
    unittest.main()
