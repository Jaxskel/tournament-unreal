#!/usr/bin/env python3
"""Read-only preflight/equivalence for the existing fixed-twelve response recipe.

Original Python parser/checker for the limited unencrypted v3 plaintext/zlib
layout. No extraction, source-file reads from response paths, or promotion.
Both commands print JSON only. Response creation remains in prepare-startup-compression.py.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys
import zlib
import types

MAX_GROWTH = 64 * 1024**2
MAX_DATA = 2 * 1024**3  # Exclusive upper bound, including non-pak container bytes.
MAX_INDEX = 64 * 1024**2
MAX_SMALL = 32 * 1024**2
MAX_ENTRIES = 200000
MAX_BLOCKS = 100000
MAX_RAW = 1024**3
PLANNER_SHA256 = 'b96373c9eae94d8b2a9e690064c5c87037b8f5f4c2e68ea30f1f931c9b83388d'
PLANNER = Path(__file__).with_name('prepare-startup-compression.py')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha256_arg(value):
    require(isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value), 'Expected lowercase SHA256')
    return value


def physical(path, missing=False):
    path = Path(os.path.abspath(path))
    for item in [*reversed(path.parents), path]:
        try:
            s = item.lstat()
        except FileNotFoundError:
            if missing and item == path:
                return path
            raise ValueError('Missing physical ancestor: ' + str(item))
        require(not stat.S_ISLNK(s.st_mode) and not getattr(s, 'st_file_attributes', 0) & 0x400,
                'Symlink/reparse path: ' + str(item))
        if stat.S_ISREG(s.st_mode):
            require(item == path and s.st_nlink == 1, 'Hardlink/non-directory ancestor')
        else:
            require(stat.S_ISDIR(s.st_mode), 'Special file')
    return path


def identity(s):
    require(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_ino, 'Regular single-link file required')
    row = dict(device=s.st_dev, inode=s.st_ino, size=s.st_size, mtime_ns=s.st_mtime_ns)
    if os.name == 'nt':
        require(type(getattr(s, 'st_birthtime_ns', None)) is int, 'Exact Windows birth time required')
        row['birthtime_ns'] = s.st_birthtime_ns
    else:
        row['ctime_ns'] = s.st_ctime_ns
    return row


def stamp(s):
    return identity(s), s.st_ctime_ns


class PinnedFile:
    """Hold the verified handle; recheck handle and physical path after all reads."""
    def __init__(self, path, expected, limit=MAX_DATA-1):
        self.path = physical(path)
        self.expected = sha256_arg(expected)
        before = stamp(self.path.stat())
        require(0 <= before[0]['size'] <= limit, 'File size budget')
        self.file = self.path.open('rb')
        try:
            self.handle = stamp(os.fstat(self.file.fileno()))
            require(self.handle[0] == before[0], 'File changed before open')
            self.path_stamp = before
            self.size = before[0]['size']
            self.check()
        except BaseException:
            self.file.close()
            raise

    def read(self, offset, size):
        require(type(offset) is int and type(size) is int and 0 <= offset <= self.size and
                0 <= size <= self.size-offset, 'File read bounds')
        self.file.seek(offset)
        result = self.file.read(size)
        require(len(result) == size, 'Short read')
        return result

    def check(self):
        # Preserve handle-first short-circuit evaluation: diagnostics use only
        # observations already required by the original equality predicates.
        def unchanged(message):
            observed_handle = stamp(os.fstat(self.file.fileno()))
            if observed_handle != self.handle:
                raise ValueError(message + ': ' + json.dumps(dict(path=str(self.path), changed='handle',
                    expected_handle=self.handle, observed_handle=observed_handle,
                    expected_path=self.path_stamp, observed_path='not-evaluated-handle-mismatch'), sort_keys=True))
            observed_path = stamp(physical(self.path).stat())
            if observed_path != self.path_stamp:
                raise ValueError(message + ': ' + json.dumps(dict(path=str(self.path), changed='path',
                    expected_handle=self.handle, observed_handle=observed_handle,
                    expected_path=self.path_stamp, observed_path=observed_path), sort_keys=True))
        unchanged('Input identity changed')
        h = hashlib.sha256()
        for offset in range(0, self.size, 1024**2):
            h.update(self.read(offset, min(1024**2, self.size-offset)))
        require(h.hexdigest() == self.expected, 'Input SHA256 differs: ' + str(self.path))
        unchanged('Input changed during hashing')

    def pin(self):
        return dict(path=str(self.path), sha256=self.expected, identity=self.handle[0],
                    path_ctime_ns=self.path_stamp[1], handle_ctime_ns=self.handle[1])

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False)+'\n').encode()


def safe_name(name):
    require(isinstance(name, str) and name and not any(ord(c) < 32 for c in name) and
            not any(c in name for c in ('\\', ':', '"')) and
            all(p not in ('', '.', '..') for p in name.split('/')), 'Unsafe archive name')
    return name


class Reader:
    def __init__(self, data):
        self.data, self.p = data, 0

    def take(self, n):
        require(0 <= n <= len(self.data)-self.p, 'Truncated index')
        result = self.data[self.p:self.p+n]
        self.p += n
        return result

    def unpack(self, fmt):
        return struct.unpack(fmt, self.take(struct.calcsize(fmt)))

    def string(self):
        n, = self.unpack('<i')
        require(0 < abs(n) <= 32768, 'Invalid string count')
        raw = self.take(abs(n)*(2 if n < 0 else 1))
        end = b'\0\0' if n < 0 else b'\0'
        require(raw.endswith(end), 'Unterminated string')
        value = raw[:-len(end)].decode('utf-16le' if n < 0 else 'utf-8')
        require('\0' not in value, 'Embedded NUL string')
        return value


class Archive:
    def __init__(self, pinned, start=0, length=None):
        self.input = pinned
        self.start = start
        self.length = pinned.size-start if length is None else length
        require(type(start) is int and type(self.length) is int and 0 <= start and
                44 <= self.length <= pinned.size-start, 'Archive slice')
        magic, version, offset, size, checksum = struct.unpack('<IIqq20s', self.read(self.length-44,44))
        require(magic == 0x5A6F12E1 and version == 3, 'Only unencrypted v3 pak supported')
        require(0 <= offset and 0 < size <= MAX_INDEX and offset+size+44 == self.length, 'Index bounds')
        data = self.read(offset,size)
        require(hashlib.sha1(data).digest() == checksum, 'Index checksum')
        self.index_sha1 = checksum.hex()
        r = Reader(data)
        self.mount = r.string()
        require(self.mount == '../../../', 'Unsupported mount')
        count, = r.unpack('<i')
        require(0 < count < MAX_ENTRIES, 'Entry count budget')
        entries, segments, names, blocks_total = [], [], set(), 0
        for _ in range(count):
            name = safe_name(r.string())
            require(name.casefold() not in names, 'Duplicate/case-colliding entry')
            names.add(name.casefold())
            begin = r.p
            at, size, rawsize, method = r.unpack('<qqqi')
            sha1 = r.take(20).hex()
            require(method in (0,1) and 0 <= at and 0 <= size and 0 <= rawsize <= MAX_RAW, 'Unsupported entry/budget')
            blocks = []
            if method:
                n, = r.unpack('<i')
                blocks_total += n
                require(0 < n < MAX_BLOCKS and blocks_total <= 1000000, 'Block count budget')
                blocks = [r.unpack('<qq') for _ in range(n)]
            encrypted, blocksize = r.unpack('<BI')
            require(encrypted == 0, 'Encrypted entry')
            header = r.p-begin
            require(at+header <= offset, 'Header outside payload area')
            serialized = data[begin:r.p]
            require(self.read(at,header) == b'\0'*8+serialized[8:], 'Local/index header mismatch')
            segments.append((at,at+header))
            if method:
                require(0 < blocksize <= 16*1024**2 and len(blocks) == (rawsize+blocksize-1)//blocksize,
                        'Block output bound/count')
                require(blocks[0][0] == at+header and all(a[1] == b[0] for a,b in zip(blocks,blocks[1:])),
                        'Noncontiguous compressed blocks')
                require(sum(b-a for a,b in blocks) == size, 'Compressed size')
            else:
                require(size == rawsize, 'Plain size')
            for a,b in blocks or [(at+header,at+header+size)]:
                require(at+header <= a <= b <= offset and (not method or 0 < b-a <= 32*1024**2), 'Payload/block bounds')
                if a != b:
                    segments.append((a,b))
            entries.append(dict(name=name, offset=at, compressed_bytes=size, uncompressed_bytes=rawsize,
                                compression=method, sha1=sha1, header_bytes=header, blocks=blocks, blocksize=blocksize))
        require(r.p == len(data), 'Index tail')
        segments.sort()
        require(not any(a[1] > b[0] for a,b in zip(segments,segments[1:])), 'Overlapping entries')
        self.entries = entries

    def read(self, offset, size):
        require(0 <= offset <= self.length and 0 <= size <= self.length-offset, 'Archive read bounds')
        return self.input.read(self.start+offset,size)

    def payload_hash(self, e):
        sha1, sha256 = hashlib.sha1(), hashlib.sha256()
        start, remaining = e['offset']+e['header_bytes'], e['compressed_bytes']
        while remaining:
            n = min(remaining,1024**2)
            raw = self.read(start,n)
            sha1.update(raw)
            sha256.update(raw)
            start, remaining = start+n, remaining-n
        require(sha1.hexdigest() == e['sha1'], 'Actual payload checksum: '+e['name'])
        return sha256.hexdigest()

    def decoded_hash(self, e):
        if not e['compression']:
            return self.payload_hash(e)
        h, remaining = hashlib.sha256(), e['uncompressed_bytes']
        for a,b in e['blocks']:
            expected = min(remaining,e['blocksize'])
            stream = zlib.decompressobj()
            raw = stream.decompress(self.read(a,b-a),expected+1)
            require(len(raw) == expected and stream.eof and not stream.unused_data and not stream.unconsumed_tail,
                    'Invalid compressed block')
            h.update(raw)
            remaining -= len(raw)
        require(remaining == 0, 'Decoded size')
        return h.hexdigest()


def inventory_sha(archive):
    return hashlib.sha256(encoded([e['name'] for e in archive.entries])).hexdigest()


def growth_bound(archive, names):
    selected = set(names)
    found = [e for e in archive.entries if e['name'] in selected]
    require(len(found) == len(names), 'Selected entries missing')
    require(all(e['compression'] == 1 for e in found), 'Selection must currently be zlib compressed')
    growth = sum(max(0,e['uncompressed_bytes']-e['compressed_bytes']) for e in found)
    require(growth <= MAX_GROWTH and archive.input.size+growth < MAX_DATA, 'Projected growth/data budget')
    return growth


def verify_archives(original,candidate,names):
    growth_bound(original,names)
    growth = candidate.length-original.length
    require(0 <= growth <= MAX_GROWTH and original.input.size+growth < MAX_DATA, 'Actual growth/data budget')
    require(original.mount == candidate.mount, 'Mount changed')
    require([e['name'] for e in original.entries] == [e['name'] for e in candidate.entries], 'Inventory/order changed')
    selected, rows = set(names), []
    for old,new in zip(original.entries,candidate.entries):
        require(old['uncompressed_bytes'] == new['uncompressed_bytes'], 'Decoded size changed')
        before,after = original.payload_hash(old),candidate.payload_hash(new)
        if old['name'] in selected:
            require(old['compression'] == 1 and new['compression'] == 0, 'Selected compression differs')
            require(original.decoded_hash(old) == after, 'Selected decoded bytes changed')
            rows.append(dict(name=old['name'],decoded_sha256=after))
        else:
            require(old['compression'] == new['compression'] and old['blocksize'] == new['blocksize'], 'Unselected method changed')
            relative = lambda e: [(a-e['offset'],b-e['offset']) for a,b in e['blocks']]
            require(relative(old) == relative(new) and before == after, 'Unselected framing/payload changed')
    return dict(status='byte-equivalent',promotion=False,entries=len(original.entries),selected=rows,growth_bytes=growth,
                projected_data_bytes=original.input.size+growth,original_index_sha1=original.index_sha1,
                candidate_index_sha1=candidate.index_sha1,scope='All payload checksums; selected decoded bytes; unselected exact payload/framing. No runtime or startup performance claim.')


def load_planner(pinned):
    # Reuse the reviewed sibling implementation directly, without .pyc writes or
    # a import-time read of mutable source after its digest has been checked.
    raw = pinned.read(0,pinned.size)
    require(hashlib.sha256(raw).hexdigest() == PLANNER_SHA256, 'Planner source differs')
    module = types.ModuleType('fixed_startup_response_planner')
    module.__file__ = str(pinned.path)
    exec(compile(raw,str(pinned.path),'exec'),module.__dict__)
    require(len(module.SELECTED) == len(set(module.SELECTED)) == 12, 'Fixed planner selection differs')
    return module


def check_plan(original,response,planner):
    raw = response.read(0,response.size)
    changed,removals,count = planner.transform(raw)
    require(planner.inverse(changed,removals) == raw and len(removals) == 12, 'Response inverse differs')
    body = raw[len(planner.BOM):] if raw.startswith(planner.BOM) else raw
    names, flags_by_name = [], {}
    for line in body.splitlines():
        if not line.strip(b' \t'):
            continue
        match = planner.ROW.fullmatch(line)
        require(match is not None, 'Response parse mismatch')
        _,name = planner.paths(match[1],match[2])
        # Existing response preparation supports encryption syntax, but this
        # archive checker deliberately supports only the captured plaintext pak.
        flags = {flag[0] for flag in planner.FLAG.finditer(match[3])}
        require(b'-encrypt' not in flags, 'Encrypted response unsupported')
        flags_by_name[name] = flags
        names.append(name)
    require(len(names) == count == len(original.entries) and
            set(names) == {e['name'] for e in original.entries}, 'Response inventory differs')
    require(all(e['compression'] == 0 or b'-compress' in flags_by_name[e['name']] for e in original.entries),
            'Compressed baseline entry depends on missing per-entry -compress')
    growth = growth_bound(original,planner.SELECTED)
    return dict(schema='ut4-selective-startup-check-plan-v1',status='archive-plan-checked',promotion=False,
        archive_equivalence_verified=False,entries=count,selected=list(planner.SELECTED),selected_count=12,
        modified_lines=12,inverse_byte_exact=True,response_input_sha256=response.expected,
        response_output_sha256=hashlib.sha256(changed).hexdigest(),removed_bytes=len(raw)-len(changed),
        planner_sha256=PLANNER_SHA256,version=3,mount=original.mount,pak_start=original.start,pak_length=original.length,
        container_bytes=original.input.size,container_prefix_bytes=original.start,
        container_suffix_bytes=original.input.size-original.start-original.length,
        original_index_sha1=original.index_sha1,inventory_sha256=inventory_sha(original),
        max_growth_bytes=MAX_GROWTH,conservative_growth_bytes=growth,
        projected_data_upper_bound=original.input.size+growth,data_limit_exclusive=MAX_DATA,
        response_order_is_not_pak_index_order=True,source_paths_opened=False,unrealpak_executed=False,
        warning=planner.WARNING,limits='Preflight only. Preserve the packaging tool/order inputs separately; fresh .data and loader regeneration/validation remain separate.')


def run(args):
    with ExitStack() as stack:
        inputs = []
        def open_pin(path,sha,limit=MAX_DATA-1):
            value = stack.enter_context(PinnedFile(path,sha,limit))
            inputs.append(value)
            return value
        planner_file = open_pin(PLANNER,PLANNER_SHA256,MAX_SMALL)
        planner = load_planner(planner_file)
        baseline = open_pin(args.baseline,args.baseline_sha256)
        response = open_pin(args.response,args.response_sha256,planner.MAX_BYTES)
        old = Archive(baseline,args.pak_start,args.pak_length)
        result = check_plan(old,response,planner)
        if args.command == 'verify':
            candidate = open_pin(args.candidate,args.candidate_sha256)
            require(candidate.path != baseline.path, 'Candidate must be a distinct standalone pak')
            new = Archive(candidate)
            equivalence = verify_archives(old,new,planner.SELECTED)
            result = dict(schema='ut4-selective-startup-equivalence-v1',preflight=result,
                          archive_equivalence_verified=True,**equivalence)
        for value in inputs:
            value.check()
        result['inputs'] = [value.pin() for value in inputs]
        result['inputs_unchanged'] = True
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command',required=True)
    for command in ('check-plan','verify'):
        sub = subs.add_parser(command)
        sub.add_argument('--baseline',required=True,type=Path,help='Standalone original pak or exact containing .data')
        sub.add_argument('--baseline-sha256',required=True,type=sha256_arg)
        sub.add_argument('--pak-start',type=int,default=0)
        sub.add_argument('--pak-length',type=int,help='Default: remaining bytes of baseline')
        sub.add_argument('--response',required=True,type=Path,help='Original response before the existing fixed12 transform')
        sub.add_argument('--response-sha256',required=True,type=sha256_arg)
        if command == 'verify':
            sub.add_argument('--candidate',required=True,type=Path,help='New standalone pak; never extracted or changed')
            sub.add_argument('--candidate-sha256',required=True,type=sha256_arg)
    args = parser.parse_args(argv)
    try:
        print(json.dumps(run(args),indent=2))
        return 0
    except (OSError,ValueError,struct.error,zlib.error) as error:
        print('Selective startup archive refused: '+str(error),file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
