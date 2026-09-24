"""Suppress legacy remote stat writes only for browser builds with explicit -NoMCP.

Default: read-only preflight of one exact pinned UE4.15 source file. --apply
requires a coordinated source freeze and isolated physical source root. No
compiler, engine, backend emulation, asset or game-package operation is performed.
The guard does not report success or change stats flags. Native builds and browser
builds without -NoMCP retain the original method. A fresh build is required.
Physical/recheck/exclusive-backup conventions follow patch-browser-analytics.py;
there is no process lock or power-loss transaction guarantee.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

MARKER = 'TOURNAMENT_BROWSER_CLOUD_STATS_V1'
BACKUP = '.before-tournament-browser-cloud-stats'
ANCHOR = 'void AUTPlayerState::WriteStatsToCloud()\n{\n'
GUARD = '\t// TOURNAMENT_BROWSER_CLOUD_STATS_V1\n#if PLATFORM_HTML5_BROWSER\n\tif (FParse::Param(FCommandLine::Get(), TEXT("NoMCP")))\n\t{\n\t\treturn;\n\t}\n#endif\n'
SPECS = ((
    'UnrealTournament/Source/UnrealTournament/Private/UTPlayerState.cpp',
    'ded3d537eada4b04f89e0b9690e0fc9739ac36ad09dc55a81779ae16452a33b7',
    117366,
    '9424049a4876b4515604224d68feacb23db06079435b01f569b510e41660d418',
),)

def sha(data):
    return hashlib.sha256(data).hexdigest()


def inverse(raw, spec=SPECS[0]):
    insertion = (ANCHOR + GUARD).encode('ascii')
    if (sha(raw) != spec[3] or raw.count(insertion) != 1
            or raw.count(MARKER.encode('ascii')) != 1):
        raise ValueError('Unsupported or altered guarded source: ' + spec[0])
    original = raw.replace(insertion, ANCHOR.encode('ascii'), 1)
    if len(original) != spec[2] or sha(original) != spec[1]:
        raise ValueError('Guard inverse does not recover exact original')
    return original


def transform(raw, spec=SPECS[0]):
    if sha(raw) == spec[3]:
        inverse(raw, spec)
        return raw
    if len(raw) != spec[2] or sha(raw) != spec[1]:
        raise ValueError('Unsupported or modified complete source: ' + spec[0])
    anchor = ANCHOR.encode('ascii')
    if raw.count(anchor) != 1 or MARKER.encode('ascii') in raw:
        raise ValueError('Writer entry anchor differs')
    updated = raw.replace(anchor, anchor + GUARD.encode('ascii'), 1)
    if sha(updated) != spec[3] or inverse(updated, spec) != raw:
        raise ValueError('Guarded source hash or byte inverse differs')
    return updated


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
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.cloud-stats-backup-', delete=False) as stream:
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
        # The original is flushed and verified before source replacement.
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
                with tempfile.NamedTemporaryFile(dir=r['current']['path'].parent, prefix='.cloud-stats-patch-', delete=False) as stream:
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
    check_all()
    return {'apply': apply, 'browserOnly': True, 'requiresExplicitNoMCP': True, 'requiresFreshBuild': True,
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
