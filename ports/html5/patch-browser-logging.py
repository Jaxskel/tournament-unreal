"""Correct two log-prefix varargs types in the isolated UE4.15 CL3228288 port.

GFrameCounter is uint64, but both FormatLogLine prefixes use %3d. Cast the
modulo-1000 result to int32; do not change clocks, counters, or format strings.
Run with the compiler stopped. This script does not build or convert the engine.
"""
import argparse
import json
from pathlib import Path
import re

SOURCE_PATH = Path('Engine/Source/Runtime/Core/Private/Misc/OutputDeviceHelper.cpp')
GLOBALS_PATH = Path('Engine/Source/Runtime/Core/Public/CoreGlobals.h')
BACKUP_SUFFIX = '.before-tournament-browser-logging'
OLD_ARGUMENT = 'GFrameCounter % 1000'
NEW_ARGUMENT = 'static_cast<int32>(GFrameCounter % 1000)'
# Exact statements read from the recovered licensed source (lines 43 and 48).
OLD_CALLS = (
    'Format = FString::Printf( TEXT( "[%07.2f][%3d]" ), RealTime, GFrameCounter % 1000 );',
    'Format = FString::Printf(TEXT("[%s][%3d]"), *FDateTime::UtcNow().ToString(TEXT("%Y.%m.%d-%H.%M.%S:%s")), GFrameCounter % 1000);',
)
NEW_CALLS = tuple(call.replace(OLD_ARGUMENT, NEW_ARGUMENT) for call in OLD_CALLS)


def without_comments(text):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/'
    return re.sub(tokens, lambda match: re.sub(r'[^\r\n]', ' ', match.group())
                  if match.group().startswith(('//', '/*')) else match.group(), text)


def function_span(text):
    declaration = r'(?m)^[ \t]*FString\s+FOutputDeviceHelper::FormatLogLine\s*\([^;{]*\)\s*\{'
    matches = list(re.finditer(declaration, without_comments(text)))
    if len(matches) != 1:
        raise ValueError('Expected exactly one FormatLogLine definition')
    start = matches[0].end() - 1
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/|[{}]'
    depth = 0
    for token in re.finditer(tokens, text[start:]):
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if depth == 0:
                return start, start + token.end()
    raise ValueError('Unclosed FormatLogLine definition')


def transform(text):
    start, end = function_span(text)
    body = text[start:end]
    scanned_body = without_comments(body)
    # Only standalone source statements count, not occurrences inside comments.
    states = []
    replacements = []
    for old, new in zip(OLD_CALLS, NEW_CALLS):
        original = list(re.finditer(r'(?m)^[ \t]*' + re.escape(old) + r'[ \t]*\r?$', scanned_body))
        patched = list(re.finditer(r'(?m)^[ \t]*' + re.escape(new) + r'[ \t]*\r?$', scanned_body))
        if len(original) == 1 and not patched:
            states.append('original')
            offset = original[0].start() + original[0].group().index(old)
            replacements.append((offset, offset + len(old), new))
        elif len(patched) == 1 and not original:
            states.append('patched')
        else:
            raise ValueError('Unexpected or duplicate FormatLogLine prefix call')
    if len(set(states)) != 1:
        raise ValueError('Incomplete logging patch; expected both calls in the same state')
    if states[0] == 'patched':
        return text
    for left, right, value in sorted(replacements, reverse=True):
        body = body[:left] + value + body[right:]
    return text[:start] + body + text[end:]


def patch(root):
    root = Path(root).resolve()
    if not (root / '.tournament-browser-port').is_file():
        raise ValueError('Use only a marked isolated browser checkout')
    version = json.loads((root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    keys = ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')
    if tuple(version.get(key) for key in keys) != (4, 15, 0, 3228288):
        raise ValueError('Unsupported engine revision; expected UE4.15.0 CL3228288')
    globals_text = without_comments((root / GLOBALS_PATH).read_text(encoding='utf-8-sig'))
    if len(re.findall(r'(?m)^[ \t]*extern\s+CORE_API\s+uint64\s+GFrameCounter\s*;', globals_text)) != 1:
        raise ValueError('Expected the matching uint64 GFrameCounter declaration')
    path = root / SOURCE_PATH
    original = path.read_bytes()
    text = original.decode('utf-8-sig')
    updated = transform(text)
    if updated == text:
        print('Browser logging argument types already patched')
        return
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    if backup.exists():
        if backup.read_bytes() != original:
            raise ValueError('Backup conflicts with current unpatched source: ' + str(backup))
    else:
        with backup.open('xb') as saved:
            saved.write(original)
    encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'
    path.write_bytes(updated.encode(encoding))
    print('Both log-prefix frame arguments now match %3d; engine not rebuilt')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root')
    patch(parser.parse_args().source_root)
