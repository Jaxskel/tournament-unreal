"""Enable an explicit Windows editor Entry-reflection diagnostic without MainFrame creation.

Default mode is read-only. --apply makes an exact original backup and replaces
the one pinned UnrealEdGlobals.cpp file. No build, browser run, or asset
modification is performed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

BACKUP = '.before-tournament-entry-reflection-no-mainframe'
SPEC = {'path': 'Engine/Source/Editor/UnrealEd/Private/UnrealEdGlobals.cpp',
 'source_sha256': '67901af8bdf558018c334dfb24b17118ead98cb92066f0e033ed168abd5d5dc3',
 'source_bytes': 6260,
 'output_sha256': '9e5b2624ebd17f762e88b0c4ed88f5b15e59764911b5b2af931f07be5d70ec49',
 'output_bytes': 7283,
 'old': b'\t// Do final set up on the editor frame and show it\n\t{',
 'new': b'#if PLATFORM_WINDOWS\n\t// This explicit diagnostic keeps real rendering and the core ticker, without '
        b'a MainFrame swapchain.\n\tconst bool bTournamentEntryReflectionNoMainFrame = FApp::IsUnattended()\n'
        b'\t\t&& FParse::Param(FCommandLine::Get(), TEXT("TournamentEntryReflectionNoMainFrame"))\n\t\t&& FPars'
        b'e::Param(FCommandLine::Get(), TEXT("EntryReflectionDiagnostic"))\n\t\t&& !FParse::Param(FCommandLine::G'
        b'et(), TEXT("immersive"))\n\t\t&& !FParse::Param(FCommandLine::Get(), TEXT("VREditor"))\n\t\t&& !FParse'
        b'::Param(FCommandLine::Get(), TEXT("ForceVREditor"))\n\t\t&& !FParse::Param(FCommandLine::Get(), TEXT("A'
        b'utomatedMapBuild"))\n\t\t&& !FParse::Param(FCommandLine::Get(), TEXT("nullrhi"))\n\t\t&& !FParse::Para'
        b'm(FCommandLine::Get(), TEXT("game"));\n#else\n\tconst bool bTournamentEntryReflectionNoMainFrame = fals'
        b'e;\n#endif\n\tif (bTournamentEntryReflectionNoMainFrame)\n\t{\n\t\tUE_LOG(LogUnrealEd, Display, TEXT("To'
        b'urnament Entry reflection diagnostic: MainFrame creation skipped; real rendering retained."));\n\t}\n\t/'
        b'/ Do final set up on the editor frame and show it\n\tif (!bTournamentEntryReflectionNoMainFrame)\n\t{'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def inverse(data, spec=SPEC):
    if len(data) != spec['output_bytes'] or sha(data) != spec['output_sha256']:
        raise ValueError('Unsupported or modified patched source: ' + spec['path'])
    if data.count(spec['new']) != 1:
        raise ValueError('Expected one exact diagnostic MainFrame guard: ' + spec['path'])
    original = data.replace(spec['new'], spec['old'], 1)
    if len(original) != spec['source_bytes'] or sha(original) != spec['source_sha256']:
        raise ValueError('Patch inverse does not recover pinned original: ' + spec['path'])
    return original


def transform(data, spec=SPEC):
    if len(data) == spec['output_bytes'] and sha(data) == spec['output_sha256']:
        inverse(data, spec)
        return data
    if len(data) != spec['source_bytes'] or sha(data) != spec['source_sha256']:
        raise ValueError('Unsupported or modified complete source: ' + spec['path'])
    if data.count(spec['old']) != 1 or spec['new'] in data:
        raise ValueError('Expected exactly one unmodified MainFrame anchor')
    updated = data.replace(spec['old'], spec['new'], 1)
    if len(updated) != spec['output_bytes'] or sha(updated) != spec['output_sha256'] or inverse(updated, spec) != data:
        raise ValueError('Patched source hash or byte-exact inverse differs')
    return updated


def physical(path, missing=False):
    path = Path(os.path.abspath(path))
    for item in (*reversed(path.parents), path):
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing and item == path:
                return path
            raise ValueError('Missing physical path: ' + str(item))
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Linked/reparse path: ' + str(item))
        if stat.S_ISREG(info.st_mode):
            if item != path or info.st_nlink != 1:
                raise ValueError('Nonphysical or multiply-linked file: ' + str(item))
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('Nonregular path: ' + str(item))
    return path


def snapshot(path):
    path = physical(path)
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    ident = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_nlink)
    if ident(before) != ident(after) or len(data) != after.st_size:
        raise ValueError('File changed during read: ' + str(path))
    return {'path': path, 'data': data, 'identity': ident(after), 'mode': stat.S_IMODE(after.st_mode)}


def recheck(saved):
    current = snapshot(saved['path'])
    if current['identity'] != saved['identity'] or current['data'] != saved['data']:
        raise ValueError('File changed after preflight: ' + str(saved['path']))


def _publish_backup(saved, destination, check_all):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.entry-reflection-backup-', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(saved['data'])
            stream.flush()
            os.fsync(stream.fileno())
        if snapshot(temporary)['data'] != saved['data']:
            raise ValueError('Staged original backup verification failed')
        check_all()
        os.link(temporary, destination)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    backup = snapshot(destination)
    if backup['data'] != saved['data']:
        raise ValueError('Published original backup verification failed')
    return backup


def patch(root, apply=False, spec=SPEC):
    root = physical(root)
    marker = snapshot(root / '.tournament-browser-port')
    version = snapshot(root / 'Engine/Build/Build.version')
    build = json.loads(version['data'].decode('utf-8-sig'))
    if tuple(build.get(k) for k in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')) != (4, 15, 0, 3228288):
        raise ValueError('Expected isolated UE4.15.0 CL3228288 source root')
    current = snapshot(root / spec['path'])
    updated = transform(current['data'], spec)
    original = inverse(current['data'], spec) if sha(current['data']) == spec['output_sha256'] else current['data']
    backup_path = physical(Path(str(current['path']) + BACKUP), missing=True)
    backup = snapshot(backup_path) if backup_path.exists() else None
    if backup:
        if backup['data'] != original or sha(backup['data']) != spec['source_sha256']:
            raise ValueError('Original backup differs from exact pinned bytes')
    elif current['data'] == updated:
        raise ValueError('Already-patched source requires its exact original backup')

    def check_all():
        recheck(marker)
        recheck(version)
        recheck(current)
        if backup:
            recheck(backup)
        elif physical(backup_path, missing=True).exists():
            raise ValueError('Unexpected original backup appeared')

    check_all()
    if apply:
        if backup is None:
            backup = _publish_backup(current, backup_path, check_all)
        check_all()
        if current['data'] != updated:
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=current['path'].parent, prefix='.entry-reflection-patch-', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(updated)
                    stream.flush()
                    os.fsync(stream.fileno())
                check_all()
                os.chmod(temporary, current['mode'])
                os.replace(temporary, current['path'])
                current = snapshot(current['path'])
                if current['data'] != updated:
                    raise ValueError('Installed source differs from exact candidate bytes')
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        check_all()
    return {'apply': apply, 'entryReflectionDiagnosticOnly': True, 'requiresFreshUnrealEdBuild': True,
            'files': [{'path': spec['path'], 'sourceSha256': sha(current['data']),
                       'proposedSha256': sha(updated), 'alreadyPatched': current['data'] == updated}]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root')
    parser.add_argument('--apply', action='store_true', help='Create exact original backup and install the pinned source change')
    args = parser.parse_args()
    try:
        print(json.dumps(patch(args.source_root, args.apply), indent=2))
    except (ValueError, OSError, UnicodeError, json.JSONDecodeError) as error:
        parser.exit(1, str(error) + '\n')
