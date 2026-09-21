"""Guard the pinned legacy optimizer's outer OR-zero simplification.

Original patcher; no third-party source is bundled or printed. Default is a
read-only two-file preflight. --apply changes source only, with private original
backups. It does NOT rebuild/select optimizer.exe or change link environment.
Use only a physical, marked isolated UE4.15.0 CL3228288 / Emscripten1.36.13 root.
Usage: python3 patch-browser-optimizer.py SOURCE_ROOT [--apply]
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

SDK = Path('Engine/Extras/ThirdPartyNotUE/emsdk/emscripten/incoming')
BACKUP_SUFFIX = '.before-tournament-browser-optimizer-or-v1'
# Raw full-file hashes intentionally reject revisions and newline conversions.
SPECS = (
    dict(path=SDK / 'tools/optimizer/optimizer.cpp', line=1691,
         before='a05337b4e7261eef15927713edc8854f57f53eaeba6b5227c46b894ee6ff6a3b',
         after='a5efedd2508c450deefe0e742cdaec5770e9c153de42e9b035ea742ea95e9beb',
         guard=b'value[3][0] == NUM && value[3][1]->getNumber() == 0 && '),
    dict(path=SDK / 'tools/js-optimizer.js', line=761,
         before='b6e47b54902c4e35bbc16c894d5327adbeefef7b6fa0b5246aa40c6d48889831',
         after='fc84235158af27677e2f4b89adbef9568d88e4a304e1f775c0018d8e0bc7f96f',
         guard=b"value[3][0] === 'num' && value[3][1] === 0 && "),
)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def transform(data, spec):
    """Insert one condition, preserving every other byte; accept only pinned states."""
    fingerprint = digest(data)
    if fingerprint == spec['after']:
        return data
    if fingerprint != spec['before']:
        raise ValueError('Unsupported optimizer source fingerprint: ' + str(spec['path']))
    lines = data.splitlines(keepends=True)
    index = spec['line'] - 1
    if index >= len(lines):
        raise ValueError('Missing pinned optimizer condition')
    line = lines[index]
    if not line.lstrip().startswith(b'if (') or line.count(b'if (') != 1:
        raise ValueError('Unexpected pinned optimizer condition')
    changed = line.replace(b'if (', b'if (' + spec['guard'], 1)
    lines[index] = changed
    result = b''.join(lines)
    if digest(result) != spec['after']:
        raise ValueError('Guard did not produce the independently reviewed fingerprint')
    lines[index] = changed.replace(b'if (' + spec['guard'], b'if (', 1)
    if b''.join(lines) != data:
        raise ValueError('Optimizer transform changed unrelated bytes')
    return result


def physical(path, missing_leaf=False):
    """Reject reparse points/symlinks, hardlinked files, and special ancestors."""
    path = Path(os.path.abspath(path))
    for item in [*reversed(path.parents), path]:
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing_leaf and item == path:
                return path
            raise ValueError('Required physical path missing: ' + str(item))
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Refusing linked/reparse path: ' + str(item))
        if stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1 or item != path:
                raise ValueError('Refusing shared file or non-directory ancestor: ' + str(item))
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('Refusing special path: ' + str(item))
    return path


def validate_root(root):
    root = physical(root)
    if not physical(root / '.tournament-browser-port').is_file():
        raise ValueError('Expected a marked isolated browser checkout')
    version = json.loads(physical(root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    fields = ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')
    if not isinstance(version, dict) or tuple(version.get(k) for k in fields) != (4, 15, 0, 3228288):
        raise ValueError('Expected UE4.15.0 CL3228288')
    sdk_version = physical(root / SDK / 'emscripten-version.txt').read_text(encoding='utf-8-sig').strip().strip('"')
    if sdk_version != '1.36.13':
        raise ValueError('Expected pinned Emscripten1.36.13')
    return root


def inspect(root, spec):
    path = physical(root / spec['path'])
    if not path.is_file():
        raise ValueError('Expected regular optimizer source')
    source = path.read_bytes()
    updated = transform(source, spec)
    backup = physical(Path(str(path) + BACKUP_SUFFIX), missing_leaf=True)
    exists = backup.exists()
    if exists:
        if not backup.is_file():
            raise ValueError('Expected regular original backup')
        saved = backup.read_bytes()
        if digest(saved) != spec['before'] or transform(saved, spec) != updated:
            raise ValueError('Conflicting or altered optimizer backup')
    elif source == updated:
        raise ValueError('Patched optimizer source requires its pinned original backup')
    return dict(path=path, backup=backup, source=source, updated=updated,
                backup_exists=exists, spec=spec)


def recheck(item):
    path, backup = item['path'], item['backup']
    physical(path)
    physical(backup, missing_leaf=not item['backup_exists'])
    if path.read_bytes() != item['source'] or backup.exists() != item['backup_exists']:
        raise ValueError('Optimizer source/backup changed since preflight')
    if backup.exists() and digest(backup.read_bytes()) != item['spec']['before']:
        raise ValueError('Optimizer original backup changed since preflight')


def replace(item):
    path, backup = item['path'], item['backup']
    recheck(item)
    if not item['backup_exists']:
        with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as stream:
            stream.write(item['source'])
            stream.flush()
            os.fsync(stream.fileno())
        item['backup_exists'] = True
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.optimizer-or-patch-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(item['updated'])
            stream.flush()
            os.fsync(stream.fileno())
        recheck(item)
        os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def patch(root, apply=False):
    root = validate_root(root)
    # Validate BOTH files and backups before any mutation, including backup writes.
    plan = [inspect(root, spec) for spec in SPECS]
    changed = [item for item in plan if item['source'] != item['updated']]
    if apply and changed:
        validate_root(root)
        for item in plan:
            recheck(item)
        for item in changed:
            replace(item)
    status = 'already-patched' if not changed else ('patched' if apply else 'would-patch')
    result = dict(status=status, sourceOnly=True, nativeExecutableRebuilt=False,
                  files=[dict(file=str(item['spec']['path']), sha256=digest(item['updated'])) for item in plan])
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root', type=Path)
    parser.add_argument('--apply', action='store_true', help='back up and guard source only; never rebuild optimizer.exe')
    args = parser.parse_args()
    try:
        patch(args.source_root, args.apply)
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
