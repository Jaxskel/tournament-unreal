"""Omit redundant destroy hints only in the single-threaded HTML5 browser.

Default is read-only preflight. --apply requires a marked isolated UE4.15.0
CL3228288 checkout and preserves a private original backup. No build is run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

SOURCE_PATH = Path('Engine/Source/Runtime/Core/Private/Serialization/AsyncIOSystemBase.cpp')
BACKUP_SUFFIX = '.before-tournament-browser-asyncio'
MARKER = 'TOURNAMENT_BROWSER_ASYNCIO_HINT_V1'
INSERT = """// TOURNAMENT_BROWSER_ASYNCIO_HINT_V1
#if PLATFORM_HTML5_BROWSER
// The cache is IO-thread-owned: never inspect it from a threaded producer.
if (!FPlatformProcess::SupportsMultithreading() && BusyWithRequest.GetValue() == 0)
{
    const uint32 HintHash = FCrc::StrCrc32<TCHAR>(*FileName.ToLower());
    bool bNeedsCloseHint = FindCachedFileHandle(HintHash) != nullptr;
    for (const FAsyncIORequest& PendingRequest : OutstandingRequests)
    {
        if (!PendingRequest.bIsDestroyHandleRequest && PendingRequest.FileNameHash == HintHash)
        {
            bNeedsCloseHint = true;
            break;
        }
    }
    if (!bNeedsCloseHint)
    {
        return 0;
    }
}
#endif
"""


def scan(text):
    tokens = r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/'
    return re.sub(tokens, lambda m: re.sub(r'[^\r\n]', ' ', m.group()), text)


def method_span(text, name):
    code = scan(text)
    matches = list(re.finditer(r'\buint64\s+FAsyncIOSystemBase::' + re.escape(name) + r'\s*\([^{}]*\)\s*\{', code))
    if len(matches) != 1:
        raise ValueError('Expected one definition of ' + name)
    left = matches[0].end() - 1
    depth = 0
    for pos in range(left, len(code)):
        if code[pos] == '{': depth += 1
        elif code[pos] == '}':
            depth -= 1
            if depth == 0: return left, pos + 1
    raise ValueError('Unclosed method: ' + name)


def transform(text):
    newline = '\r\n' if '\r\n' in text else '\n'
    if newline == '\r\n' and '\n' in text.replace('\r\n', ''):
        raise ValueError('Mixed source line endings')
    left, right = method_span(text, 'QueueDestroyHandleRequest')
    body = text[left:right]
    anchor = re.search(r'(?m)^([ \t]*)FScopeLock\s+ScopeLock\(\s*CriticalSection\s*\);[ \t]*\r?$', scan(body))
    if not anchor:
        raise ValueError('Missing producer queue lock')
    insertion = ''.join(anchor[1] + line + newline for line in INSERT.splitlines())
    marked = MARKER in text
    if marked:
        if text.count(MARKER) != 1 or body.count(insertion) != 1:
            raise ValueError('Altered or misplaced AsyncIO guard')
        clean = body.replace(insertion, '', 1)
    else:
        clean = body
    # Pin the inspected hint producer's control flow; comments/spacing may vary.
    compact = re.sub(r'\s+', '', scan(clean))
    expected = ('{FScopeLockScopeLock(CriticalSection);FAsyncIORequestIORequest;'
                'IORequest.RequestIndex=RequestIndex++;IORequest.FileName=FileName;'
                'IORequest.FileNameHash=FCrc::StrCrc32<TCHAR>(*FileName.ToLower());'
                'IORequest.Priority=AIOP_MIN;IORequest.bIsDestroyHandleRequest=true;'
                'if(GbLogAsyncLoading==true){LogIORequest(TEXT(),IORequest);}'
                'OutstandingRequests.Add(IORequest);OutstandingRequestsEvent->Trigger();'
                'returnIORequest.RequestIndex;}')
    if compact != expected:
        raise ValueError('Unknown destroy-hint producer shape')
    # Matching pending reads are stable under the same producer lock.
    a, b = method_span(text, 'QueueIORequest')
    producer = re.sub(r'\s+', '', scan(text[a:b]))
    lock = 'FScopeLockScopeLock(CriticalSection);'
    enqueue = 'OutstandingRequests.Add(IORequest);'
    if producer.count(lock) != 1 or producer.count(enqueue) != 1 or producer.index(lock) > producer.index(enqueue):
        raise ValueError('Read producer no longer enqueues under the expected lock')
    clean_anchor = re.search(r'(?m)^([ \t]*)FScopeLock\s+ScopeLock\(\s*CriticalSection\s*\);[ \t]*\r?$', scan(clean))
    point = clean.index('\n', clean_anchor.end()) + 1
    updated = clean[:point] + insertion + clean[point:]
    if marked:
        if updated != body: raise ValueError('AsyncIO guard is not directly inside the producer lock')
        return text
    return text[:left] + updated + text[right:]


def physical(path, missing_leaf=False):
    """Check every ancestor before reading/writing: no reparse or hardlinked files."""
    path = Path(os.path.abspath(path))
    chain = [*reversed(path.parents), path]
    for item in chain:
        try:
            info = item.lstat()
        except FileNotFoundError:
            if missing_leaf and item == path:
                return path
            raise ValueError('Required physical path missing: ' + str(item))
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Refusing linked/reparse path: ' + str(item))
        if stat.S_ISREG(info.st_mode):
            if info.st_nlink != 1:
                raise ValueError('Refusing multiply-linked file: ' + str(item))
            if item != path:
                raise ValueError('Non-directory ancestor: ' + str(item))
        elif not stat.S_ISDIR(info.st_mode):
            raise ValueError('Refusing non-regular path: ' + str(item))
    return path


def patch(root, apply=False):
    root = Path(os.path.abspath(root))
    marker = physical(root / '.tournament-browser-port')
    if not marker.is_file():
        raise ValueError('Use only a marked isolated browser checkout')
    version = json.loads(physical(root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if tuple(version.get(k) for k in ('MajorVersion', 'MinorVersion', 'PatchVersion', 'Changelist')) != (4, 15, 0, 3228288):
        raise ValueError('Expected UE4.15.0 CL3228288')
    path = physical(root / SOURCE_PATH)
    original = path.read_bytes()
    encoding = 'utf-8-sig' if original.startswith(b'\xef\xbb\xbf') else 'utf-8'
    updated = transform(original.decode(encoding)).encode(encoding)
    backup = physical(Path(str(path) + BACKUP_SUFFIX), missing_leaf=True)
    if backup.exists():
        saved = backup.read_bytes()
        saved_encoding = 'utf-8-sig' if saved.startswith(b'\xef\xbb\xbf') else 'utf-8'
        if MARKER in saved.decode(saved_encoding):
            raise ValueError('Backup must contain original, unpatched source')
        if original != updated:
            if saved != original:
                raise ValueError('Conflicting original backup')
        elif transform(saved.decode(saved_encoding)).encode(saved_encoding) != original:
            raise ValueError('Patched source does not match original backup')
    elif original == updated:
        raise ValueError('Patched source is missing its original backup')
    status = 'already-patched' if original == updated else 'would-patch'
    if apply and original != updated:
        if not backup.exists():
            with backup.open('xb') as stream:
                stream.write(original)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.asyncio-patch-', delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(updated)
            physical(path)
            if path.read_bytes() != original:
                raise ValueError('Source changed during patch; refusing replacement')
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
            os.replace(temporary, path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        status = 'patched'
    result = {'status': status, 'file': str(SOURCE_PATH), 'sha256': hashlib.sha256(updated).hexdigest()}
    print(json.dumps(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root')
    parser.add_argument('--apply', action='store_true', help='save the original and apply the single-thread browser hint guard')
    args = parser.parse_args()
    try:
        patch(args.source_root, args.apply)
    except (ValueError, OSError, UnicodeError) as error:
        parser.exit(1, str(error) + '\n')
