"""Read-only exact one-entry pak replacement proof; no whole-map acceptance."""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
import types

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
PARSER = HERE/'selective-startup-pak.py'
PARSER_SHA256 = '1767b4da70cab0b980d30448ee35632d3afd307ecce0befa891a60bbbb09b6ca'
ENTRY = 'UnrealTournament/Content/RestrictedAssets/Maps/UT-Entry.umap'
MAX_BYTES = 2**31 - 1


def need(ok, message):
    if not ok:
        raise ValueError(message)


def load_parser(path):
    raw = Path(path).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == PARSER_SHA256, 'Parser pin')
    module = types.ModuleType('pinned_entry_archive')
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def verify(original, candidate, cooked):
    """Count-independent core for synthetic fixtures; CLI requires exactly 9179."""
    need(original.mount == candidate.mount, 'Mount changed')
    names = [e['name'] for e in original.entries]
    need(names == [e['name'] for e in candidate.entries], 'Inventory/order changed')
    need(len(names) == len(set(names)) and names.count(ENTRY) == 1, 'Exact Entry required')
    replacement = None
    for old, new in zip(original.entries, candidate.entries):
        need(old['compression'] == new['compression'], 'Compression method changed')
        before, after = original.payload_hash(old), candidate.payload_hash(new)
        decoded_before, decoded_after = original.decoded_hash(old), candidate.decoded_hash(new)
        if old['name'] == ENTRY:
            need(new['uncompressed_bytes'] == cooked.size and decoded_after == cooked.expected,
                 'Entry differs from pinned cooked file')
            need(decoded_before != decoded_after, 'Entry unchanged')
            replacement = dict(name=ENTRY, old_decoded_sha256=decoded_before,
                               new_decoded_sha256=decoded_after, bytes=cooked.size,
                               compression=new['compression'])
        else:
            relative = lambda e: [(a-e['offset'], b-e['offset']) for a,b in e['blocks']]
            need(old['uncompressed_bytes'] == new['uncompressed_bytes'] and
                 old['compressed_bytes'] == new['compressed_bytes'] and
                 old['header_bytes'] == new['header_bytes'] and old['blocksize'] == new['blocksize'] and
                 relative(old) == relative(new) and before == after and decoded_before == decoded_after,
                 'Non-Entry payload/framing changed: '+old['name'])
    return dict(schema='ut4-entry-replacement-v1', status='one-entry-replacement-verified',
                entries=len(names), unchanged_entries=len(names)-1, replacement=replacement,
                mount=original.mount, whole_map_acceptance=False, visual_success=False, promotion=False,
                scope='Exact archive inventory/order/methods; other entries stored framing and decoded hashes equal; Entry equals pinned cooked bytes. No map semantic or runtime acceptance.')


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--parser', type=Path, default=PARSER)
    for name in ('baseline', 'candidate', 'cooked-entry'):
        ap.add_argument('--'+name, type=Path, required=True)
        ap.add_argument('--'+name+'-sha256', required=True)
    args = ap.parse_args(argv)
    try:
        p = load_parser(args.parser)
        with ExitStack() as stack:
            parser_pin = stack.enter_context(p.PinnedFile(args.parser, PARSER_SHA256, p.MAX_SMALL))
            pins = [stack.enter_context(p.PinnedFile(getattr(args, n.replace('-', '_')), getattr(args, n.replace('-', '_')+'_sha256'), MAX_BYTES))
                    for n in ('baseline', 'candidate', 'cooked-entry')]
            need(len({(x.handle[0]['device'], x.handle[0]['inode']) for x in pins}) == 3,
                 'Inputs must be distinct physical files')
            old, new = p.Archive(pins[0]), p.Archive(pins[1])
            need(len(old.entries) == len(new.entries) == 9179, 'Exactly 9179 entries required')
            result = verify(old, new, pins[2])
            for pin in [parser_pin, *pins]:
                pin.check()  # Rehash retained handles and recheck paths before emitting success.
            result.update(inputs=[x.pin() for x in pins], parser_sha256=PARSER_SHA256, inputs_unchanged=True)
        print(json.dumps(result, allow_nan=False))
        return 0
    except (OSError, ValueError, AssertionError) as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
