"""Disable legacy Epic telemetry initialization only in the local browser build.

Default: read-only two-file preflight. Apply requires the operator's coordinated
source freeze; this script does not own a process lock or run a compiler.
Native/editor behavior and UT's local parameter-name initialization are retained.
Backups are flushed and verified before replacement. This is not a power-loss
transaction: directory-entry persistence is platform-dependent.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

MARKER = 'TOURNAMENT_BROWSER_EPIC_ANALYTICS_V1'
BACKUP = '.before-tournament-browser-analytics'
ENGINE_IF = '#if UE_BUILD_DEBUG || (PLATFORM_XBOXONE && UE_BUILD_SHIPPING)'
ENGINE_NEW = '// ' + MARKER + '\n' + ENGINE_IF.replace('#if ', '#if PLATFORM_HTML5_BROWSER || ', 1)
UT_START = '\tif (!Analytics.IsValid())'
UT_END = '\tInitializeAnalyticParameterNames();'
UT_OPEN = '\t// ' + MARKER + '\n#if !PLATFORM_HTML5_BROWSER\n'
UT_CLOSE = '#endif // ' + MARKER + '\n'
SPECS = (
    ('Engine/Source/Runtime/Engine/Private/EngineAnalytics.cpp',
     'd8603a782edff3d090c0dc4c159c4184d53104ecdf5487636ff1b78c00aaac22', 'engine'),
    ('UnrealTournament/Source/UnrealTournament/Private/UTAnalytics.cpp',
     '0f7260b724430fe13b53676c52f416b924800ee4ad9dd460046a4a4ae3698753', 'game'),
)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def transform(raw, spec):
    encoding = 'utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'
    text = raw.decode(encoding)
    newline = '\r\n' if '\r\n' in text else '\n'
    text = text.replace('\r\n', '\n')
    if '\r' in text or (newline == '\r\n' and '\n' in raw.decode(encoding).replace('\r\n', '')):
        raise ValueError('Mixed source line endings')
    clean = text
    if MARKER in text:
        if spec[2] == 'engine':
            if text.count(ENGINE_NEW) != 1 or text.count(MARKER) != 1:
                raise ValueError('Altered engine analytics guard')
            clean = text.replace(ENGINE_NEW, ENGINE_IF, 1)
        else:
            if text.count(UT_OPEN + UT_START) != 1 or text.count(UT_CLOSE + UT_END) != 1 or text.count(MARKER) != 2:
                raise ValueError('Altered UT analytics guard')
            clean = text.replace(UT_OPEN, '', 1).replace(UT_CLOSE, '', 1)
    if sha(clean.encode()) != spec[1]:
        raise ValueError('Unsupported or modified complete source: ' + spec[0])
    if spec[2] == 'engine':
        if clean.count(ENGINE_IF) != 1:
            raise ValueError('Engine initialization anchor differs')
        updated = clean.replace(ENGINE_IF, ENGINE_NEW, 1)
    else:
        if clean.count(UT_START) != 1 or clean.count(UT_END) != 1 or clean.index(UT_START) >= clean.index(UT_END):
            raise ValueError('UT initialization anchors differ')
        updated = clean.replace(UT_START, UT_OPEN + UT_START, 1).replace(UT_END, UT_CLOSE + UT_END, 1)
    if MARKER in text and updated != text:
        raise ValueError('Guard location differs')
    return updated.replace('\n', newline).encode(encoding)

def physical(path, missing=False):
    path = Path(os.path.abspath(path))
    for p in (*reversed(path.parents), path):
        try:
            info = p.lstat()
        except FileNotFoundError:
            if missing and p == path:
                return path
            raise ValueError('Missing physical path: ' + str(p))
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked/reparse path: ' + str(p))
        if stat.S_ISREG(info.st_mode):
            if p != path or info.st_nlink != 1:
                raise ValueError('Nonphysical or multiply-linked file: ' + str(p))
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('Nonregular path: ' + str(p))
    return path

def snapshot(path):
    path = physical(path)
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_nlink)
    if identity(before) != identity(after) or len(data) != after.st_size:
        raise ValueError('File changed during read')
    return {'path': path, 'data': data, 'identity': identity(after), 'mode': stat.S_IMODE(after.st_mode)}

def recheck(saved):
    current = snapshot(saved['path'])
    if current['identity'] != saved['identity'] or current['data'] != saved['data']:
        raise ValueError('File changed after preflight: ' + str(saved['path']))

def publish_backup(saved, destination, check_all):
    # Publish only a complete, verified file, exclusively. A failed write/fsync
    # leaves no final backup to obstruct the next preflight. The temporary hard
    # link is removed before physical single-link validation of the final name.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.analytics-backup-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(saved['data']); stream.flush(); os.fsync(stream.fileno())
        if snapshot(temporary)['data'] != saved['data']:
            raise ValueError('Staged backup verification failed')
        check_all()
        os.link(temporary, destination)  # Fails if destination exists; never overwrites.
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    backup = snapshot(destination)
    if backup['data'] != saved['data']:
        raise ValueError('Backup verification failed')
    return backup

def patch(root, apply=False, specs=SPECS):
    root = physical(root)
    marker = snapshot(root / '.tournament-browser-port')
    version = snapshot(root / 'Engine/Build/Build.version')
    v = json.loads(version['data'].decode('utf-8-sig'))
    if tuple(v.get(k) for k in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')) != (4, 15, 0, 3228288):
        raise ValueError('Expected isolated UE4.15.0 CL3228288')
    rows = []
    for spec in specs:
        current = snapshot(root / spec[0])
        updated = transform(current['data'], spec)
        backup_path = physical(Path(str(current['path']) + BACKUP), missing=True)
        backup = snapshot(backup_path) if backup_path.exists() else None
        if backup:
            if MARKER.encode() in backup['data'] or transform(backup['data'], spec) != updated:
                raise ValueError('Original backup differs')
            if current['data'] != updated and backup['data'] != current['data']:
                raise ValueError('Backup does not preserve exact original bytes')
        elif current['data'] == updated:
            raise ValueError('Patched source requires original backup')
        rows.append({'spec': spec, 'current': current, 'updated': updated, 'backup': backup, 'backup_path': backup_path})

    def check_all():
        recheck(marker); recheck(version)
        for r in rows:
            recheck(r['current'])
            if r['backup']:
                recheck(r['backup'])
            elif physical(r['backup_path'], missing=True).exists():
                raise ValueError('Unexpected backup appeared')

    if apply:
        check_all()
        # Both originals are flushed and verified before source replacement.
        # Interrupted source replacement is recoverable; never roll back.
        for r in rows:
            if r['backup'] is None:
                r['backup'] = publish_backup(r['current'], r['backup_path'], check_all)
        check_all()
        for r in rows:
            if r['current']['data'] == r['updated']:
                continue
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=r['current']['path'].parent, prefix='.analytics-patch-', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(r['updated']); stream.flush(); os.fsync(stream.fileno())
                check_all()
                os.chmod(temporary, r['current']['mode'])
                os.replace(temporary, r['current']['path'])
                r['current'] = snapshot(r['current']['path'])
                if r['current']['data'] != r['updated']:
                    raise ValueError('Installed source differs')
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        check_all()
    return {'apply': apply, 'browserOnly': True, 'requiresFreshBuild': True,
            'files': [{'path': r['spec'][0], 'sourceSha256': sha(r['current']['data']),
                       'proposedSha256': sha(r['updated']), 'alreadyPatched': r['current']['data'] == r['updated']}
                      for r in rows]}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root'); parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        print(json.dumps(patch(args.source_root, args.apply), indent=2))
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
