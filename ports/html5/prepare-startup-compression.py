"""Prepare the fixed twelve-entry, opt-in startup compression response recipe.

Default: read a caller-SHA256-pinned response and print a JSON plan. --output
creates only that new response file, exclusively; parents are never created.
No source assets are opened, and no cook, engine or UnrealPak process is run.
UTF-8 (optional BOM), LF/CRLF and all bytes outside the twelve removal spans
are preserved. Each span is -compress plus its single preceding separator byte.
This is response preparation, not archive equivalence or promotion approval.
On an output I/O failure a partial new file may remain; it is never overwritten.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


SELECTED = (
    'UnrealTournament/Content/RestrictedAssets/Character/Malcom_New/Textures/T_Malcolm_Head_T_2.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/Flak/Textures/T_FlakCannon_AGD.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/Flak/Textures/T_FlakCannon_Color.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/Flak/Textures/T_FlakCannon_N.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/Global/Weapon_Skins/Flak_Cannon/T_Flak_Skin_BW.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/Global/Weapon_Skins/Link_Gun/T_Link_Skin_BW.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/GrenadeLauncher/Textures/T_Grenade_Launcher_Color.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/LinkGun/Textures/Old_Textures/T_Link_Grime_M.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/LinkGun/Textures/T_Link_ADG.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/RocketLauncher/Textures/T_Rocket_Launcher_D.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/RocketLauncher/Textures/T_Rocket_Launcher_M2.uasset',
    'UnrealTournament/Content/RestrictedAssets/Weapons/Sniper/Textures/T_Sniper_D.uasset',
)
MAX_BYTES = 16 * 1024 * 1024
MAX_LINE_BYTES = 16 * 1024
MAX_PATH_BYTES = 4096
MAX_ENTRIES = 100000
BOM = b'\xef\xbb\xbf'
ROW = re.compile(rb'[ \t]*"([^"\r\n]+)"[ \t]+"([^"\r\n]+)"((?:[ \t]+-[a-z]+)*[ \t]*)')
FLAG = re.compile(rb'-[a-z]+')
SUPPORTED_FLAGS = {b'-compress', b'-encrypt'}
RESERVED = re.compile(r'(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', re.I)
WARNING = 'Do not pass global -compress to UnrealPak: it would recompress the twelve selected entries.'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def path_parts(value):
    require(0 < len(value) <= MAX_PATH_BYTES, 'Path byte limit')
    text = value.decode('utf-8')
    require(not any(ord(c) < 32 or ord(c) == 127 or c in '<>"|?*' for c in text), 'Unsafe path character')
    return text


def canonical_parts(text):
    parts = text.split('/')
    require(all(p and p not in ('.', '..') and not p.endswith((' ', '.'))
                and not RESERVED.fullmatch(p) for p in parts), 'Noncanonical/unsafe path component')
    require(':' not in text, 'Unsafe path colon')
    return parts


def paths(source, destination):
    src = path_parts(source).replace('\\', '/')
    if re.match(r'^[A-Za-z]:/', src):
        source_parts = canonical_parts(src[3:])
    else:
        require(src.startswith('/') and not src.startswith('//'), 'Source must be an absolute local path')
        source_parts = canonical_parts(src[1:])
    dest = path_parts(destination)
    require(dest.startswith('../../../') and '\\' not in dest, 'Destination must use the ../../../ pak mount')
    name = dest[9:]
    dest_parts = canonical_parts(name)
    # This UnrealPak derives the stored basename from Source, not Dest.
    require(source_parts[-1] == dest_parts[-1], 'Source/destination basename mismatch')
    return src.casefold(), name


def inverse(output, removals):
    """Restore recorded spans without decoding or normalizing any response bytes."""
    restored = output
    removed = sum(len(token) for _, token in removals)
    for start, token in reversed(removals):
        removed -= len(token)
        position = start - removed
        restored = restored[:position] + token + restored[position:]
    return restored


def transform(raw):
    require(0 < len(raw) <= MAX_BYTES, 'Response byte limit')
    # Validate the whole encoding, including blank lines, without re-encoding it.
    raw.decode('utf-8-sig')
    body = raw[len(BOM):] if raw.startswith(BOM) else raw
    offset = len(raw) - len(body)
    sources, destinations, selected, removals = set(), set(), set(), []
    entries = 0
    for number, line in enumerate(body.splitlines(keepends=True), 1):
        require(len(line) <= MAX_LINE_BYTES, f'Line {number}: line byte limit')
        if line.endswith(b'\r\n'):
            content = line[:-2]
        elif line.endswith(b'\n'):
            content = line[:-1]
        else:
            content = line
        require(b'\r' not in content and b'\n' not in content, f'Line {number}: unsupported line ending')
        if content.strip(b' \t'):
            match = ROW.fullmatch(content)
            require(match is not None, f'Line {number}: expected quoted source, destination and supported flags')
            source, name = paths(match[1], match[2])
            require(source not in sources, f'Line {number}: duplicate source')
            require(name.casefold() not in destinations, f'Line {number}: duplicate destination')
            sources.add(source)
            destinations.add(name.casefold())
            entries += 1
            require(entries <= MAX_ENTRIES, 'Entry count limit')
            flags = list(FLAG.finditer(match[3]))
            values = [f[0] for f in flags]
            require(set(values) <= SUPPORTED_FLAGS, f'Line {number}: unknown flag')
            require(len(values) == len(set(values)), f'Line {number}: duplicate flag')
            if name in SELECTED:
                require(values.count(b'-compress') == 1, f'Line {number}: selected entry must have exactly one -compress: {name}')
                selected.add(name)
                flag = next(f for f in flags if f[0] == b'-compress')
                start = offset + match.start(3) + flag.start() - 1
                end = offset + match.start(3) + flag.end()
                require(raw[start:start+1] in (b' ', b'\t'), 'Missing flag separator')
                removals.append((start, raw[start:end]))
        offset += len(line)
    require(selected == set(SELECTED), 'Missing selected entries: ' + ', '.join(sorted(set(SELECTED) - selected)))
    pieces, previous = [], 0
    for start, token in removals:
        pieces.append(raw[previous:start])
        previous = start + len(token)
    pieces.append(raw[previous:])
    output = b''.join(pieces)
    require(len(removals) == 12 and inverse(output, removals) == raw, 'Inverse byte mismatch')
    return output, removals, entries


def read_response(path):
    # Refuse devices/FIFOs; the bounded read also catches growth after stat.
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NONBLOCK', 0))
    with os.fdopen(fd, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= MAX_BYTES, 'Expected a bounded regular response file')
        raw = stream.read(MAX_BYTES + 1)
    require(0 < len(raw) <= MAX_BYTES, 'Response byte limit')
    return raw


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path, help='Existing UTF-8 UnrealPak response file')
    parser.add_argument('--input-sha256', required=True, help='Caller-verified SHA256 of the exact input bytes')
    parser.add_argument('--output', type=Path, help='Explicit opt-in: create this NEW response exclusively')
    args = parser.parse_args(argv)
    try:
        require(re.fullmatch(r'[0-9a-fA-F]{64}', args.input_sha256) is not None, 'Expected a 64-digit input SHA256')
        raw = read_response(args.input)
        require(sha256(raw) == args.input_sha256.lower(), 'Input SHA256 mismatch')
        output, removals, entries = transform(raw)
        require(read_response(args.input) == raw, 'Input changed during preparation')
        if args.output is not None:
            # O_EXCL also refuses existing symlinks, hard links, and the input.
            with args.output.open('xb') as stream:
                require(stream.write(output) == len(output), 'Short response write')
                stream.flush()
                os.fsync(stream.fileno())
        result = dict(schema='ut4-startup-compression-response-v1',
                      status='response-only-written' if args.output is not None else 'response-only-plan',
                      input=str(args.input), output=str(args.output) if args.output is not None else None,
                      input_sha256=sha256(raw), output_sha256=sha256(output),
                      entries=entries, selected=list(SELECTED), selected_count=len(removals),
                      removed_bytes=len(raw)-len(output), inverse_byte_exact=True,
                      archive_equivalence_verified=False, promotion=False, warning=WARNING)
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError) as error:
        print('Startup compression response refused: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
