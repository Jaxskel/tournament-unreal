"""Read-only comparison of matching legacy file_packager output and staging files."""
import argparse
import hashlib
import json
import re
from pathlib import Path, PurePosixPath


def digest_slice(stream, start, count):
    stream.seek(start)
    digest = hashlib.sha256()
    while count:
        chunk = stream.read(min(count, 4 * 1024 * 1024))
        if not chunk:
            raise ValueError('Unexpected end of file')
        digest.update(chunk)
        count -= len(chunk)
    return digest.hexdigest()


def verify(loader, archive, stage):
    text = loader.read_text(encoding='utf-8-sig')
    matches = re.findall(r'^\s*loadPackage\((\{.*\})\);\s*$', text, re.MULTILINE)
    if len(matches) != 1:
        raise ValueError('Expected exactly one literal loadPackage metadata object')
    metadata = json.loads(matches[0])
    size = archive.stat().st_size
    if metadata['remote_package_size'] != size:
        raise ValueError('Package size does not match metadata')
    end = 0
    entries = []
    seen = set()
    with archive.open('rb') as data:
        for item in metadata['files']:
            name = item['filename']
            posix = PurePosixPath(name)
            if not name.startswith('/') or '..' in posix.parts or '\\' in name or name in seen:
                raise ValueError('Unsafe or duplicate metadata path')
            seen.add(name)
            if item.get('crunched') or type(item['start']) is not int or type(item['end']) is not int:
                raise ValueError('Unsupported encoded or malformed slice')
            if item['start'] != end or not end <= item['end'] <= size:
                raise ValueError('Invalid/noncontiguous slice')
            count = item['end'] - end
            staged = stage.joinpath(*posix.parts[1:]).resolve()
            if not staged.is_relative_to(stage.resolve()) or not staged.is_file() or staged.stat().st_size != count:
                raise ValueError('Staged file absent or size differs: ' + name)
            actual = digest_slice(data, end, count)
            with staged.open('rb') as source:
                expected = digest_slice(source, 0, count)
            if actual != expected:
                raise ValueError('Packaged bytes differ from stage: ' + name)
            entries.append({'name': name, 'bytes': count, 'sha256': actual})
            end = item['end']
        if end != size:
            raise ValueError('Metadata does not cover the complete archive')
        archive_hash = digest_slice(data, 0, size)
    return {'archive': str(archive), 'bytes': size, 'sha256': archive_hash,
            'sliceComparisonsPassed': True, 'entries': entries,
            'scope': 'Exact staged-byte equivalence only; inspect/test pak and required maps separately'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('loader', type=Path)
    parser.add_argument('archive', type=Path)
    parser.add_argument('stage', type=Path)
    args = parser.parse_args()
    print(json.dumps(verify(args.loader, args.archive, args.stage), indent=2))
