"""Synthetic v3 files only; no engine/assets, packaging process or real 2GB scan."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location('selective_startup',Path(__file__).with_name('selective-startup-pak.py'))
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)
with P.PinnedFile(P.PLANNER,P.PLANNER_SHA256,P.MAX_SMALL) as pin:
    PLANNER = P.load_planner(pin)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def string(text):
    raw = text.encode()+b'\0'
    return struct.pack('<i',len(raw))+raw


def pak(rows,version=3,encrypted=0,blocksize=64,mount='../../../'):
    content = bytearray()
    index = string(mount)+struct.pack('<i',len(rows))
    for name,raw,compressed in rows:
        offset = len(content)
        pieces = [zlib.compress(raw[i:i+64]) for i in range(0,len(raw),64)] if compressed else [raw]
        payload = b''.join(pieces)
        header_size = 53+(4+16*len(pieces) if compressed else 0)
        tail = struct.pack('<qqi',len(payload),len(raw),int(compressed))+hashlib.sha1(payload).digest()
        if compressed:
            tail += struct.pack('<i',len(pieces))
            cursor = offset+header_size
            for piece in pieces:
                tail += struct.pack('<qq',cursor,cursor+len(piece))
                cursor += len(piece)
        tail += struct.pack('<BI',encrypted,blocksize if compressed else 0)
        content += struct.pack('<q',0)+tail+payload
        index += string(name)+struct.pack('<q',offset)+tail
    return bytes(content)+index+struct.pack('<IIqq20s',0x5A6F12E1,version,len(content),len(index),hashlib.sha1(index).digest())


def response(rows,flags=None):
    flags = flags or {}
    return PLANNER.BOM+b'\r\n'+b''.join(
        ('"C:/Synthetic Cook/'+name+'" "../../../'+name+'"'+flags.get(name,' -compress')+'\r\n').encode()
        for name,_,_ in reversed(rows))


class SelectivePak(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.rows = [(name,b'abcd'*1024,True) for name in PLANNER.SELECTED]
        self.rows += [('Other/Keep.uasset',b'other'*500,True),('Other/Plain.uasset',b'plain',False)]
        self.candidate = [(n,r,False if n in PLANNER.SELECTED else c) for n,r,c in self.rows]

    def file(self,name,raw):
        path = self.root/name
        path.write_bytes(raw)
        return path

    def archive(self,name,rows=None,raw=None,prefix=b'',suffix=b''):
        raw = pak(rows) if raw is None else raw
        path = self.file(name,prefix+raw+suffix)
        pin = P.PinnedFile(path,sha(prefix+raw+suffix))
        self.addCleanup(pin.close)
        return P.Archive(pin,len(prefix),len(raw))

    def response_pin(self,raw=None):
        raw = response(self.rows) if raw is None else raw
        path = self.file('response.txt',raw)
        pin = P.PinnedFile(path,sha(raw),PLANNER.MAX_BYTES)
        self.addCleanup(pin.close)
        return pin

    def test_fixed_planner_reuse_inverse_bom_crlf_and_inventory_set_not_order(self):
        old = self.archive('old',self.rows,prefix=b'prefix',suffix=b'suffix')
        pin = self.response_pin()
        result = P.check_plan(old,pin,PLANNER)
        raw = response(self.rows)
        changed,removals,count = PLANNER.transform(raw)
        self.assertEqual(result['response_output_sha256'],sha(changed))
        self.assertEqual(PLANNER.inverse(changed,removals),raw)
        self.assertTrue(changed.startswith(PLANNER.BOM))
        self.assertEqual(result['entries'],count)
        self.assertEqual(result['selected'],list(PLANNER.SELECTED))
        self.assertEqual((result['container_prefix_bytes'],result['container_suffix_bytes']),(6,6))
        self.assertEqual(result['projected_data_upper_bound'],old.input.size+sum(len(r)-e['compressed_bytes'] for (_,r,c),e in zip(self.rows,old.entries) if e['name'] in PLANNER.SELECTED))

    def test_all_payloads_selected_decode_unselected_identical_after_offsets_shift(self):
        result = P.verify_archives(self.archive('old',self.rows),self.archive('new',self.candidate),PLANNER.SELECTED)
        self.assertEqual(result['entries'],14)
        self.assertEqual(len(result['selected']),12)
        self.assertEqual(result['selected'][0]['decoded_sha256'],sha(self.rows[0][1]))
        self.assertFalse(result['promotion'])

    def test_valid_checksum_changed_selected_content_rejected(self):
        changed = self.candidate[:]
        changed[0] = (changed[0][0],b'efgh'*1024,False)
        with self.assertRaisesRegex(ValueError,'Selected decoded'):
            P.verify_archives(self.archive('old',self.rows),self.archive('new',changed),PLANNER.SELECTED)

    def test_valid_checksum_changed_unselected_content_rejected(self):
        changed = self.candidate[:]
        changed[-2] = ('Other/Keep.uasset',b'OTHER'*500,True)
        with self.assertRaisesRegex(ValueError,'Unselected framing/payload'):
            P.verify_archives(self.archive('old',self.rows),self.archive('new',changed),PLANNER.SELECTED)

    def test_corrupt_actual_payload_and_local_header_rejected(self):
        raw = bytearray(pak(self.candidate))
        raw[53] ^= 1
        with self.assertRaisesRegex(ValueError,'payload checksum'):
            P.verify_archives(self.archive('old',self.rows),self.archive('bad',raw=bytes(raw)),PLANNER.SELECTED)
        raw = bytearray(pak(self.candidate))
        raw[8] ^= 1
        with self.assertRaisesRegex(ValueError,'Local/index'):
            self.archive('header',raw=bytes(raw))

    def test_index_checksum_tail_version_encryption_mount_and_block_bounds(self):
        original = pak(self.rows)
        damaged = bytearray(original)
        damaged[-45] ^= 1
        cases = [bytes(damaged),original[:-1],pak(self.rows,version=4),pak(self.rows,encrypted=1),
                 pak(self.rows,mount='Other/'),pak(self.rows,blocksize=0),pak(self.rows,blocksize=17*1024**2)]
        for i,raw in enumerate(cases):
            with self.subTest(i=i),self.assertRaises(ValueError):
                self.archive('bad'+str(i),raw=raw)

    def test_valid_checksum_invalid_zlib_and_overexpansion_rejected(self):
        compress = zlib.compress
        for i,payload in enumerate([compress(b'x'*64)+b'tail',compress(b'x'*64)[:-1],compress(b'x'*1000)]):
            with patch('zlib.compress',return_value=payload):
                raw = pak([('A.uasset',b'x'*64,True)])
            old = self.archive('zlib'+str(i),raw=raw)
            old.payload_hash(old.entries[0])
            with self.subTest(i=i),self.assertRaisesRegex(ValueError,'Invalid compressed block'):
                old.decoded_hash(old.entries[0])

    def test_inventory_order_method_and_selected_actual_compression(self):
        old = self.archive('old',self.rows)
        with self.assertRaisesRegex(ValueError,'Inventory/order'):
            P.verify_archives(old,self.archive('order',list(reversed(self.candidate))),PLANNER.SELECTED)
        changed = self.candidate[:]
        changed[-2] = ('Other/Keep.uasset',changed[-2][1],False)
        with self.assertRaisesRegex(ValueError,'Unselected method'):
            P.verify_archives(old,self.archive('method',changed),PLANNER.SELECTED)
        plain = self.archive('plain',self.candidate)
        with self.assertRaisesRegex(ValueError,'currently be zlib'):
            P.check_plan(plain,self.response_pin(),PLANNER)

    def test_response_inventory_missing_selected_encryption_and_global_dependency(self):
        old = self.archive('old',self.rows)
        cases = [response(self.rows)+b'"C:/Other/Extra" "../../../Other/Extra" -compress\r\n',
                 response(self.rows[1:]),response(self.rows,{self.rows[0][0]:' -compress -encrypt'}),
                 response(self.rows,{'Other/Keep.uasset':''})]
        for i,raw in enumerate(cases):
            with self.subTest(i=i),self.assertRaises(ValueError):
                P.check_plan(old,self.response_pin(raw),PLANNER)
        # Plain archive entry with a compress request is legitimate: packager may decline it.
        P.check_plan(old,self.response_pin(response(self.rows)),PLANNER)

    def test_growth_and_full_container_limit_include_suffix(self):
        old = self.archive('old',self.rows,prefix=b'a'*17,suffix=b'b'*29)
        pin = self.response_pin()
        growth = P.growth_bound(old,PLANNER.SELECTED)
        with patch.object(P,'MAX_GROWTH',growth-1),self.assertRaisesRegex(ValueError,'growth/data'):
            P.check_plan(old,pin,PLANNER)
        with patch.object(P,'MAX_DATA',old.input.size+growth),self.assertRaisesRegex(ValueError,'growth/data'):
            P.check_plan(old,pin,PLANNER)
        with patch.object(P,'MAX_DATA',old.input.size+growth+1):
            P.check_plan(old,pin,PLANNER)

    def test_bounded_index_count_string_and_rawsize(self):
        with self.assertRaises(ValueError):
            P.Reader(struct.pack('<i',40000)).string()
        with patch.object(P,'MAX_INDEX',1),self.assertRaisesRegex(ValueError,'Index bounds'):
            self.archive('index',self.rows)
        with patch.object(P,'MAX_ENTRIES',12),self.assertRaisesRegex(ValueError,'Entry count'):
            self.archive('count',self.rows)
        with patch.object(P,'MAX_RAW',10),self.assertRaisesRegex(ValueError,'budget'):
            self.archive('raw',self.rows)

    def test_unsafe_duplicate_names_and_overlapping_entry(self):
        for i,name in enumerate(['../x','/absolute','x\\y','a:stream']):
            with self.subTest(name=name),self.assertRaises(ValueError):
                self.archive('unsafe'+str(i),[(name,b'x',False)])
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            self.archive('duplicate',[('A',b'x',False),('a',b'x',False)])
        # Identical indexed/local metadata at offset zero passes header equality;
        # the index then names the same physical range twice and must fail overlap.
        raw = pak([('A',b'x',False),('B',b'x',False)])
        index_offset = struct.unpack('<q',raw[-36:-28])[0]
        data = bytearray(raw[index_offset:-44])
        r = P.Reader(data);r.string();r.unpack('<i');r.string();r.take(53);r.string()
        struct.pack_into('<q',data,r.p,0)
        bad = raw[:index_offset]+data+struct.pack('<IIqq20s',0x5A6F12E1,3,index_offset,len(data),hashlib.sha1(data).digest())
        with self.assertRaisesRegex(ValueError,'Overlapping'):
            self.archive('overlap',raw=bad)

    def cli_fixture(self,command):
        old = self.file('baseline.data',b'prefix'+pak(self.rows)+b'suffix')
        rsp = self.file('input.txt',response(self.rows))
        args = [command,'--baseline',str(old),'--baseline-sha256',sha(old.read_bytes()),'--pak-start','6',
                '--pak-length',str(len(pak(self.rows))),'--response',str(rsp),'--response-sha256',sha(rsp.read_bytes())]
        if command == 'verify':
            new = self.file('candidate.pak',pak(self.candidate))
            args += ['--candidate',str(new),'--candidate-sha256',sha(new.read_bytes())]
        return args

    def cli(self,args):
        out,err = io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code = P.main(args)
        return code,out.getvalue(),err.getvalue()

    def test_both_commands_readonly_no_sources_opened_or_files_created(self):
        for command in ('check-plan','verify'):
            args = self.cli_fixture(command)
            before = {p.name:p.read_bytes() for p in self.root.iterdir()}
            code,out,err = self.cli(args)
            self.assertEqual((code,err),(0,''))
            result = json.loads(out)
            self.assertTrue(result['inputs_unchanged'])
            self.assertEqual(result['archive_equivalence_verified'],command=='verify')
            self.assertEqual({p.name:p.read_bytes() for p in self.root.iterdir()},before)

    def test_bad_pins_and_input_drift_emit_no_success(self):
        args = self.cli_fixture('verify')
        bad = args[:];bad[bad.index('--candidate-sha256')+1]='0'*64
        self.assertEqual(self.cli(bad)[0:2],(1,''))
        original = P.check_plan
        def drift(*values):
            result = original(*values)
            with (self.root/'input.txt').open('ab') as out:
                out.write(b'\n')
            return result
        with patch.object(P,'check_plan',drift):
            code,out,err = self.cli(args)
        self.assertEqual((code,out),(1,''))
        self.assertIn('identity changed',err)

    def test_identity_diagnostics_keep_single_observations_and_short_circuit(self):
        path = self.file('tiny-pin',b'content')
        with P.PinnedFile(path,sha(b'content')) as pin:
            for during in (False,True):
                for changed in ('handle','path'):
                    expected = pin.handle if changed == 'handle' else pin.path_stamp
                    observed = (dict(expected[0]),expected[1]+1)
                    observed[0]['mtime_ns'] += 1
                    calls = ([pin.handle,pin.path_stamp] if during else [])
                    calls += [observed] if changed == 'handle' else [pin.handle,observed]
                    with self.subTest(during=during,changed=changed), \
                         patch.object(P,'stamp',side_effect=calls) as stamps, \
                         self.assertRaises(ValueError) as caught:
                        pin.check()
                    self.assertEqual(stamps.call_count,len(calls))
                    message,payload = str(caught.exception).split(': ',1)
                    self.assertEqual(message,'Input changed during hashing' if during else 'Input identity changed')
                    detail = json.loads(payload)
                    self.assertEqual(detail['path'],str(path))
                    self.assertEqual(detail['changed'],changed)
                    self.assertEqual(detail['expected_'+changed],json.loads(json.dumps(expected)))
                    self.assertEqual(detail['observed_'+changed],json.loads(json.dumps(observed)))
                    if changed == 'handle':
                        self.assertEqual(detail['observed_path'],'not-evaluated-handle-mismatch')
                    else:
                        self.assertEqual(detail['observed_handle'],json.loads(json.dumps(pin.handle)))
            # Hash mismatch still precedes the final stamps; no new observations.
            pin.expected='0'*64
            with patch.object(P,'stamp',side_effect=[pin.handle,pin.path_stamp]) as stamps, \
                 self.assertRaisesRegex(ValueError,'Input SHA256 differs'):
                pin.check()
            self.assertEqual(stamps.call_count,2)

    def test_replacement_metadata_guard_independent_of_platform_rename(self):
        path = self.file('identity-original',b'123')
        replacement = self.file('identity-other',b'123')
        with P.PinnedFile(path,sha(b'123')) as pin:
            # Common deterministic guard coverage, separate from whether this
            # OS permits replacing a path while its old read handle is open.
            replacement_stamp = P.stamp(replacement.stat())
            self.assertNotEqual(replacement_stamp[0]['inode'],pin.path_stamp[0]['inode'])
            with patch.object(P,'stamp',side_effect=[pin.handle,replacement_stamp]) as stamps, \
                 self.assertRaisesRegex(ValueError,'Input identity changed') as refused:
                pin.check()
            self.assertEqual(stamps.call_count,2)
            self.assertEqual(json.loads(str(refused.exception).split(': ',1)[1])['changed'],'path')
            pin.check()  # Actual path/handle remained unchanged by the fixture.

    def test_identity_replacement_links_and_slice_bounds_fail_closed(self):
        path = self.file('p',b'123')
        with P.PinnedFile(path,sha(b'123')) as pin:
            replacement = self.file('other',b'123')
            if os.name == 'nt':
                # CRT read handles deny deletion: a failed rename is NOT proof
                # that the checker detected an actual filesystem replacement.
                with self.assertRaises(PermissionError) as denied:
                    os.replace(replacement,path)
                self.assertIn(denied.exception.winerror,(5,32))
                self.assertEqual(path.read_bytes(),b'123')
                self.assertEqual(replacement.read_bytes(),b'123')
                pin.check()
            else:
                os.replace(replacement,path)
                with self.assertRaises(ValueError):
                    pin.check()
        link = self.root/'link';link.symlink_to(path)
        with self.assertRaises(ValueError):
            P.PinnedFile(link,sha(b'123'))
        hard = self.root/'hard';os.link(path,hard)
        with self.assertRaises(ValueError):
            P.PinnedFile(path,sha(b'123'))
        old = self.archive('old',self.rows)
        for start,length in [(-1,None),(1,old.length),(0,43)]:
            with self.subTest(start=start,length=length),self.assertRaises(ValueError):
                P.Archive(old.input,start,length)


if __name__ == '__main__':
    unittest.main()
