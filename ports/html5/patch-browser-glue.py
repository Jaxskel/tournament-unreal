"""Fix two JS/native string bounds in the marked UE4.15 CL3228288 checkout.

Apply with the compiler stopped. Only the culture capacity check and URL buffer
allocation change; LocationString ownership is deliberately left unchanged.
Run: python3 patch-browser-glue.py /path/to/isolated/browser-port
"""
import argparse
import json
from pathlib import Path
import re

CULTURE_PATH = Path('Engine/Source/Runtime/HTML5/HTML5JS/Private/HTML5JavaScriptFx.js')
URL_PATH = Path('Engine/Source/Runtime/HTML5/MapPakDownloader/Private/MapPakDownloader.cpp')
BACKUP_SUFFIX = '.before-tournament-browser-glue'

CULTURE_FUNCTION = r'\bUE_GetCurrentCultureName\s*:\s*function\s*\(\s*address\s*,\s*outsize\s*\)\s*\{'
URL_FUNCTION = r'\bFMapPakDownloader::Init\s*\([^)]*\)\s*\{'
CULTURE_OLD = r'culture_name\.lenght\s*>=\s*outsize'
CULTURE_NEW = "typeof culture_name !== 'string' || culture_name.length >= outsize"
URL_NEW = 'hoststring.length + 1'


def function_span(text, declaration):
    matches = list(re.finditer(declaration, text))
    if len(matches) != 1:
        raise ValueError('Expected exactly one target function declaration')
    start = matches[0].end() - 1
    # Ignore braces in comments and quoted C++/embedded-JS strings.
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/|[{}]'
    depth = 0
    for token in re.finditer(tokens, text[start:]):
        if token.group() == '{':
            depth += 1
        elif token.group() == '}':
            depth -= 1
            if depth == 0:
                return start, start + token.end()
    raise ValueError('Unclosed target function')


def replace_guarded(text, declaration, pattern, old, new):
    start, end = function_span(text, declaration)
    body = text[start:end]
    matches = list(re.finditer(pattern, body))
    if len(matches) != 1:
        raise ValueError('Expected exactly one original or fully patched bounds block')
    match = matches[0]
    value = match.group('value')
    if value == new:
        return text
    if not re.fullmatch(old, value):
        raise ValueError('Unexpected or incomplete bounds patch')
    left, right = match.span('value')
    return text[:start + left] + new + text[start + right:]


def culture(text):
    condition = '(?:' + CULTURE_OLD + '|' + re.escape(CULTURE_NEW) + ')'
    pattern = (r'var\s+culture_name\s*=\s*navigator\.language\s*\|\|\s*navigator\.browserLanguage\s*;\s*'
               r'if\s*\(\s*(?P<value>' + condition + r')\s*\)\s*'
               r'(?:return\s+0\s*;|\{\s*return\s+0\s*;\s*\})\s*'
               r'Module\.writeAsciiToMemory\(\s*culture_name\s*,\s*address\s*\)\s*;\s*return\s+1\s*;')
    return replace_guarded(text, CULTURE_FUNCTION, pattern, CULTURE_OLD, CULTURE_NEW)


def url(text):
    # Match the full JS block inside Init, not every malloc in the source file.
    pattern = (r'var\s+hoststring\s*=\s*location\.href\.substring\(\s*0\s*,\s*'
               r'location\.href\.lastIndexOf\(\s*(?:"/"|\'/\')\s*\)\s*\)\s*;\s*'
               r'var\s+buffer\s*=\s*Module\._malloc\(\s*(?P<value>hoststring\.length(?: \+ 1)?)\s*\)\s*;\s*'
               r'Module\.writeAsciiToMemory\(\s*hoststring\s*,\s*buffer\s*\)\s*;\s*return\s+buffer\s*;')
    return replace_guarded(text, URL_FUNCTION, pattern, r'hoststring\.length', URL_NEW)


def patch(root):
    root = Path(root).resolve()
    if not (root / '.tournament-browser-port').is_file():
        raise ValueError('Use only a marked isolated browser checkout')
    version = json.loads((root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if tuple(version.get(key) for key in ('MajorVersion', 'MinorVersion', 'Changelist')) != (4, 15, 3228288):
        raise ValueError('Unsupported engine revision; expected UE4.15 CL3228288')

    plan = []
    # Validate both source files and existing backups before writing either file.
    for relative, transform in ((CULTURE_PATH, culture), (URL_PATH, url)):
        path = root / relative
        original = path.read_bytes()
        text = original.decode('utf-8-sig')
        updated = transform(text)
        if updated == text:
            continue
        encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'
        backup = path.with_name(path.name + BACKUP_SUFFIX)
        if backup.exists() and backup.read_bytes() != original:
            raise ValueError('Backup conflicts with current unpatched source: ' + str(backup))
        plan.append((path, backup, original, updated.encode(encoding)))

    for path, backup, original, updated in plan:
        if not backup.exists():
            with backup.open('xb') as saved:
                saved.write(original)
    for path, backup, original, updated in plan:
        path.write_bytes(updated)
    print('Browser glue bounds patched' if plan else 'Browser glue bounds already patched')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root')
    patch(parser.parse_args().source_root)
