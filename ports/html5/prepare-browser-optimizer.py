"""Prepare the guarded legacy optimizer and perform a provably fresh UE link.

Windows execution only; --help is portable. No third-party source is bundled.
prepare validates all eleven inputs, applies the separate two-file source guard,
and builds/verifies a fingerprinted private native executable. link always backs
up JS/BC/mem/symbols before UBT: this intentionally costs a full link each call.
All compiler overrides belong to subprocess environment copies, never the caller.
Failed/partial generations remain quarantined; only a validated set gets a receipt.
Timeout/interrupt stops and drains the owned process tree before quarantine or
unlock. Unconfirmed drain retains the lock and leaves live output paths in place.
The BOpt/16-hex layout follows a successful controlled shorter-path configure
comparison; this exact prepare layout still needs Windows verification. No exact
MAX_PATH threshold is claimed; receipts always validate the full hash.
"""
import argparse
import contextlib
import contextvars
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

HERE = Path(__file__).resolve().parent
PIN_FILE = HERE / 'optimizer-source-pins.json'
PINS = json.loads(PIN_FILE.read_text())
module = importlib.util.spec_from_file_location('optimizer_source_guard', HERE / 'patch-browser-optimizer.py')
GUARD = importlib.util.module_from_spec(module)
module.loader.exec_module(GUARD)
CONTROLS = ('Ready', 'SessionEpoch', 'Width', 'Height', 'Frame', 'SetResolution',
            'SetSensitivity', 'SetVolume', 'ReleaseInput')
PROBE = '''function orProbe(x,m){x=x|0;m=m|0;var y=0;y=(x=1,x|0)|m;return y|0;}
function zeroProbe(x){x=x|0;var y=0;y=(x=1,x|0)|0;return y|0;}
function leftZeroProbe(x){x=x|0;var y=0;y=0|(x=1,x|0);return y|0;}
function effectProbe(x){x=x|0;var y=0;y=(x=1,x|0)|(rhs()|0);return y|0;}
// EMSCRIPTEN_GENERATED_FUNCTIONS
'''
VERIFY = '''var fs=require('fs'),vm=require('vm'),assert=require('assert');
var calls=0,c={rhs:function(){calls++;return 2;}};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),c);
[0,-2147483648,2,-1].forEach(function(m){assert.strictEqual(c.orProbe(7,m),1|m);});
assert.strictEqual(c.zeroProbe(7),1);assert.strictEqual(c.leftZeroProbe(7),1);
assert.strictEqual(c.effectProbe(7),3);assert.strictEqual(calls,1);
console.log('OPTIMIZER_RHS_GUARD_PASS');
'''


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def file(path):
    path = GUARD.physical(path)
    if not path.is_file():
        raise ValueError('Expected a physical regular file: ' + str(path))
    return path


def directory(path):
    path = Path(os.path.abspath(path))
    if not path.exists():
        directory(path.parent)
        GUARD.physical(path, missing_leaf=True)
        path.mkdir()
    if not GUARD.physical(path).is_dir():
        raise ValueError('Expected physical directory: ' + str(path))
    return path


def atomic_json(path, value):
    GUARD.physical(path, missing_leaf=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, mode='w', encoding='utf-8') as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


ACTIVE_LOCKS = contextvars.ContextVar('optimizer_active_locks', default=())


class WriterToken:
    """Registered before spawn; unknown ownership is never safe to release."""
    def __init__(self):
        self.drained = False
        self.tree = None


class LockLease:
    def __init__(self):
        self.writers = []

    @property
    def unsafe(self):
        return any(not writer.drained for writer in self.writers)


def register_writer():
    writer = WriterToken()
    for lease in ACTIVE_LOCKS.get():
        lease.writers.append(writer)
    return writer


@contextlib.contextmanager
def lock(path):
    GUARD.physical(path, missing_leaf=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    lease = LockLease()
    context = ACTIVE_LOCKS.set((*ACTIVE_LOCKS.get(), lease))
    try:
        yield lease
    finally:
        try:
            active_error = sys.exc_info()[0] is not None
            if lease.unsafe or has_undrained_error(sys.exc_info()[1]):
                print('Retaining process-tree lock: ' + str(path), file=sys.stderr)
            else:
                release_lock(path, active_error)
        finally:
            ACTIVE_LOCKS.reset(context)


def release_lock(path, active_error):
    try:
        path.unlink()
    except OSError as error:
        if not active_error:
            raise
        print('Lock cleanup failed: ' + str(error), file=sys.stderr)


class UndrainedProcessError(RuntimeError):
    """Owned writers may remain: preserve the lock and do not move artifacts."""


def has_undrained_error(error):
    """Keep ownership even if signal restoration replaces the drain exception.

    Inspect both chains (including suppressed context). Cycles terminate; an
    excessively large graph is inconclusive, so conservatively retain ownership.
    """
    pending, seen = [error], set()
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        if isinstance(current, UndrainedProcessError) or len(seen) >= 64:
            return True
        seen.add(id(current))
        pending.extend((current.__cause__, current.__context__))
    return False


@contextlib.contextmanager
def ignore_interrupts():
    # Cleanup must not be interrupted halfway through ownership/drain. The first
    # KeyboardInterrupt is re-raised only after every owned writer has stopped.
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


# The bootstrap cannot launch a compiler until it has joined our job. Assigning
# an already-running compiler from the parent would have a child-creation race.
# Its own job handle closes before compiler creation; only the supervisor holds
# the kill-on-close handle, including if the supervisor exits unexpectedly.
WINDOWS_BOOTSTRAP = r'''
import ctypes, json, subprocess, sys
from ctypes import wintypes as W
k = ctypes.WinDLL('kernel32', use_last_error=True)
k.OpenJobObjectW.argtypes = [W.DWORD, W.BOOL, W.LPCWSTR]
k.OpenJobObjectW.restype = W.HANDLE
k.GetCurrentProcess.restype = W.HANDLE
k.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
k.AssignProcessToJobObject.restype = W.BOOL
k.CloseHandle.argtypes = [W.HANDLE]
k.CloseHandle.restype = W.BOOL
job = k.OpenJobObjectW(1, False, sys.argv[1])
if not job:
    raise ctypes.WinError(ctypes.get_last_error())
try:
    if not k.AssignProcessToJobObject(job, k.GetCurrentProcess()):
        raise ctypes.WinError(ctypes.get_last_error())
finally:
    k.CloseHandle(job)
sys.exit(subprocess.call(json.loads(sys.argv[2]), stdin=subprocess.DEVNULL))
'''


class WindowsJob:
    """Win32 job accounting, not a PID/name scan; breakaway is never allowed.

    https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
    ActiveProcesses==0 is required even after TerminateJobObject succeeds.
    """
    def __init__(self):
        import ctypes as C
        from ctypes import wintypes as W
        self.C, self.W = C, W
        self.k = C.WinDLL('kernel32', use_last_error=True)
        self.name = 'Local\\TournamentOptimizer-' + uuid.uuid4().hex
        self.handle = None
        # Fixed-width LARGE_INTEGER/DWORD and pointer-width SIZE_T/ULONG_PTR.
        class BasicLimit(C.Structure):
            _fields_ = [('ProcessTime', C.c_int64), ('JobTime', C.c_int64), ('LimitFlags', W.DWORD),
                        ('MinWorkingSet', C.c_size_t), ('MaxWorkingSet', C.c_size_t),
                        ('ActiveProcessLimit', W.DWORD), ('Affinity', C.c_size_t),
                        ('PriorityClass', W.DWORD), ('SchedulingClass', W.DWORD)]
        class IoCounters(C.Structure):
            _fields_ = [(name, C.c_uint64) for name in ('ReadOps', 'WriteOps', 'OtherOps', 'ReadBytes', 'WriteBytes', 'OtherBytes')]
        class ExtendedLimit(C.Structure):
            _fields_ = [('BasicLimit', BasicLimit), ('Io', IoCounters), ('ProcessMemory', C.c_size_t),
                        ('JobMemory', C.c_size_t), ('PeakProcessMemory', C.c_size_t), ('PeakJobMemory', C.c_size_t)]
        class Accounting(C.Structure):
            _fields_ = [(name, C.c_int64) for name in ('TotalUser', 'TotalKernel', 'PeriodUser', 'PeriodKernel')] + [
                (name, W.DWORD) for name in ('PageFaults', 'TotalProcesses', 'ActiveProcesses', 'TerminatedProcesses')]
        self.Accounting = Accounting
        for name, arguments, result in (
            ('CreateJobObjectW', [C.c_void_p, W.LPCWSTR], W.HANDLE),
            ('SetInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            ('QueryInformationJobObject', [W.HANDLE, C.c_int, C.c_void_p, W.DWORD, C.c_void_p], W.BOOL),
            ('TerminateJobObject', [W.HANDLE, W.UINT], W.BOOL),
            ('OpenProcess', [W.DWORD, W.BOOL, W.DWORD], W.HANDLE),
            ('IsProcessInJob', [W.HANDLE, W.HANDLE, C.POINTER(W.BOOL)], W.BOOL),
            ('QueryFullProcessImageNameW', [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)], W.BOOL),
            ('TerminateProcess', [W.HANDLE, W.UINT], W.BOOL),
            ('WaitForSingleObject', [W.HANDLE, W.DWORD], W.DWORD),
            ('CloseHandle', [W.HANDLE], W.BOOL)):
            function = getattr(self.k, name)
            function.argtypes, function.restype = arguments, result
        self.handle = self.k.CreateJobObjectW(None, self.name)
        if not self.handle:
            raise C.WinError(C.get_last_error())
        limit = ExtendedLimit()
        limit.BasicLimit.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.k.SetInformationJobObject(self.handle, 9, C.byref(limit), C.sizeof(limit)):
            error = C.WinError(C.get_last_error())
            self.close()
            raise error

    def active(self):
        info = self.Accounting()
        if not self.k.QueryInformationJobObject(self.handle, 1, self.C.byref(info), self.C.sizeof(info), None):
            raise self.C.WinError(self.C.get_last_error())
        return info.ActiveProcesses != 0

    def terminate(self):
        if not self.k.TerminateJobObject(self.handle, 1):
            raise self.C.WinError(self.C.get_last_error())

    def pids(self):
        # JOBOBJECT_BASIC_PROCESS_ID_LIST: two DWORDs then ULONG_PTR entries.
        # Growth/retry is bounded; incomplete snapshots never authorize action.
        capacity = 16
        while capacity <= 4096:
            buffer = self.C.create_string_buffer(8 + capacity * self.C.sizeof(self.C.c_size_t))
            if self.k.QueryInformationJobObject(self.handle, 3, buffer, len(buffer), None):
                assigned, count = (self.W.DWORD * 2).from_buffer(buffer)
                if count > capacity or assigned != count:
                    raise RuntimeError('Incomplete owned-job PID snapshot')
                return list((self.C.c_size_t * count).from_buffer(buffer, 8))
            if self.C.get_last_error() != 234:  # ERROR_MORE_DATA
                raise self.C.WinError(self.C.get_last_error())
            capacity *= 2
        raise RuntimeError('Owned-job PID snapshot exceeds bounded capacity')

    def open_member(self, pid):
        # Stable handle, never terminate by a PID that could have been reused.
        handle = self.k.OpenProcess(0x1000 | 0x100000 | 1, False, pid)
        if not handle:
            raise self.C.WinError(self.C.get_last_error())
        return WindowsMember(self, pid, handle)

    def close(self):
        if self.handle:
            if not self.k.CloseHandle(self.handle):
                raise self.C.WinError(self.C.get_last_error())
            self.handle = None


class WindowsMember:
    def __init__(self, job, pid, handle):
        self.job, self.pid, self.handle = job, pid, handle

    def alive(self):
        status = self.job.k.WaitForSingleObject(self.handle, 0)
        if status not in (0, 258):
            raise self.job.C.WinError(self.job.C.get_last_error())
        return status == 258

    def in_job(self):
        result = self.job.W.BOOL()
        if not self.job.k.IsProcessInJob(self.handle, self.job.handle, self.job.C.byref(result)):
            raise self.job.C.WinError(self.job.C.get_last_error())
        return bool(result.value)

    def image(self):
        capacity = self.job.W.DWORD(32768)
        buffer = self.job.C.create_unicode_buffer(capacity.value)
        if not self.job.k.QueryFullProcessImageNameW(self.handle, 0, buffer, self.job.C.byref(capacity)):
            raise self.job.C.WinError(self.job.C.get_last_error())
        return buffer.value

    def terminate(self):
        if not self.job.k.TerminateProcess(self.handle, 1):
            raise self.job.C.WinError(self.job.C.get_last_error())

    def wait(self, timeout):
        status = self.job.k.WaitForSingleObject(self.handle, max(0, int(timeout * 1000)))
        if status == 258:
            raise TimeoutError('Pinned helper did not exit within remaining deadline')
        if status != 0:
            raise self.job.C.WinError(self.job.C.get_last_error())

    def close(self):
        if self.handle:
            if not self.job.k.CloseHandle(self.handle):
                raise self.job.C.WinError(self.job.C.get_last_error())
            self.handle = None


def retire_vctip(job, policy, audit, timeout=30):
    """Only a completed CMake command may retire its pinned telemetry child.

    Microsoft BuildXL identifies VCTIP as a surviving compiler child:
    https://github.com/microsoft/BuildXL/blob/main/Public/Sdk/Experimental/Msvc/VisualCpp/visualCpp.dsc
    Unlike its breakaway policy, we keep membership and still require job zero.
    """
    if not policy:
        return False
    deadline = time.monotonic() + timeout
    expected = os.path.normcase(os.path.abspath(policy['path']))
    if Path(expected).name.lower() != 'vctip.exe':
        raise ValueError('Only an explicit pinned VCTIP policy is supported')
    with contextlib.ExitStack() as handles:
        approved = []
        try:
            for pid in job.pids():
                member = job.open_member(pid)
                handles.callback(member.close)
                item = dict(pid=pid, action='inspect')
                audit.append(item)
                if not member.alive() or not member.in_job():
                    item['action'] = 'unconfirmed-member'
                    return False
                path = member.image()
                item['image'] = path
                if os.path.normcase(os.path.abspath(path)) != expected:
                    item['action'] = 'unapproved-image'
                    return False
                item['sha256'] = sha(file(path))
                if item['sha256'] != policy['sha256']:
                    item['action'] = 'hash-mismatch'
                    return False
                approved.append((member, item))
        except (OSError, ValueError, RuntimeError) as error:
            audit.append(dict(action='unconfirmed-snapshot', error=str(error)))
            return False
        # All observed members qualify before any is terminated. Recheck stable
        # handles; a new, unclassified descendant stays in the job and must exit
        # normally (or cause failure), never gets a success-path whole-job kill.
        for member, item in approved:
            if not member.alive() or not member.in_job():
                item['action'] = 'changed-member'
                return False
            if (os.path.normcase(os.path.abspath(member.image())) != expected
                    or sha(file(policy['path'])) != policy['sha256']):
                item['action'] = 'changed-image'
                return False
        for member, item in approved:
            member.terminate()
            item['action'] = 'terminate-pinned-helper'
        for member, item in approved:
            member.wait(max(0, deadline - time.monotonic()))
            item['exited'] = True
        return bool(approved)


class ProcessTree:
    def __init__(self, argv, cwd, env, stream):
        self.job = None
        self.process = None
        self.survivor_policy = None
        self.audit = None
        try:
            if os.name == 'nt':
                self.job = WindowsJob()
                command = [sys.executable, '-I', '-S', '-c', WINDOWS_BOOTSTRAP, self.job.name, json.dumps(argv)]
                self.process = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                                stdout=stream, stderr=subprocess.STDOUT,
                                                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                # Portable local regression path; production builds are Windows.
                self.process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                                stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
        except BaseException:
            self.close()
            raise

    def active(self):
        parent_active = self.process.poll() is None
        if self.job:
            return self.job.active() or parent_active
        try:
            os.killpg(self.process.pid, 0)
            return True
        except ProcessLookupError:
            return parent_active

    def terminate(self):
        if self.job:
            # Stop the bootstrap first, including the pre-assignment window, so
            # it cannot add a new compiler after job termination/accounting.
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=30)
            self.job.terminate()
        else:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            self.process.wait(timeout=30)

    def close(self):
        if self.job:
            self.job.close()


def wait_tree(tree, argv, timeout):
    deadline = time.monotonic() + timeout
    while tree.active():
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(argv, timeout)
        time.sleep(0.05)
    return tree.process.wait()


def monitor_command(tree, argv, timeout):
    """Command policy only; wait_tree remains the separate, pure drain proof."""
    deadline = time.monotonic() + timeout
    next_inspection = 0
    while True:
        code = tree.process.poll()
        tree.audit['primaryExit'] = code
        if code is not None and code != 0:
            raise subprocess.CalledProcessError(code, argv)
        if not tree.active():
            return max(0, deadline - time.monotonic())
        now = time.monotonic()
        if now >= deadline:
            raise subprocess.TimeoutExpired(argv, timeout)
        if code == 0 and tree.job and tree.survivor_policy and now >= next_inspection:
            retire_vctip(tree.job, tree.survivor_policy, tree.audit['helpers'], min(30, deadline - now))
            next_inspection = now + 1  # Bound inspection/audit growth.
        time.sleep(0.05)


def run(argv, cwd, env, log, timeout=600, survivor=None):
    argv = list(map(str, argv))
    with log.open('wb') as stream:
        # Outer leases retain this token even if an interrupt prevents entry
        # into cleanup, before any UndrainedProcessError could be constructed.
        writer = register_writer()
        tree = None
        audit = dict(schema=1, command=argv, primaryExit=None, job=None, parentPid=None,
                     survivorPolicy=survivor, helpers=[])
        try:
            # Ownership protection must include __exit__ restoring SIGINT: a
            # pending interrupt there already has a live tree to drain.
            with ignore_interrupts():
                tree = ProcessTree(argv, cwd, env, stream)
                writer.tree = tree
                tree.survivor_policy, tree.audit = survivor, audit
                audit['job'] = tree.job.name if tree.job and isinstance(tree.job.name, str) else None
                audit['parentPid'] = tree.process.pid if isinstance(tree.process.pid, int) else None
            remaining = monitor_command(tree, argv, timeout)
            code = wait_tree(tree, argv, remaining)
            writer.drained = True
            audit['primaryExit'] = code
        except BaseException as primary:
            if tree is None:
                raise
            # Do not quarantine or unlock until termination AND accounting prove
            # there are no owned writers left. On drain failure the lock remains.
            with ignore_interrupts():
                try:
                    tree.terminate()
                    wait_tree(tree, argv, 30)
                    writer.drained = True
                except BaseException as cleanup:
                    raise UndrainedProcessError('Owned process tree could not be drained; keep lock/artifacts in place: ' + str(cleanup)) from primary
                finally:
                    try:
                        tree.close()
                    except OSError as close_error:
                        print('Owned job handle close failed: ' + str(close_error), file=sys.stderr)
            raise
        else:
            tree.close()
        finally:
            # Separate sidecar: optimized JS stdout must contain only optimizer
            # output. Audit failure must not replace a primary command failure.
            active_error = sys.exc_info()[0] is not None
            audit['drained'] = writer.drained
            try:
                final_code = tree.process.poll() if tree is not None else None
                audit['finalParentExit'] = final_code if isinstance(final_code, int) else None
                atomic_json(log.with_name(log.name + '.process.json'), audit)
            except (OSError, ValueError, TypeError) as audit_error:
                if not active_error:
                    raise
                print('Process audit write failed: ' + str(audit_error), file=sys.stderr)
    if code:
        raise RuntimeError('Command failed (%s); see %s' % (code, log))

def capture(argv):
    return subprocess.check_output(list(map(str, argv)), text=True, encoding='utf-8', errors='replace', timeout=30).strip()


def compiler_clear():
    if os.name != 'nt':
        raise ValueError('Execute only on Windows with the inspected legacy SDK')
    script = "$p=@(Get-CimInstance Win32_Process | Where-Object {$_.Name -match '^(clang\\+\\+|clang|llc|opt|llvm-link|link|cl|UnrealBuildTool|ShaderCompileWorker|UE4Editor-Cmd)\\.exe$' -or $_.CommandLine -match '[e]mcc(\\.py)?\\s'}); if($p.Count){exit 1}"
    subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script], check=True, timeout=30)


def sources(root, guarded=False):
    root = GUARD.validate_root(root)
    with contextlib.redirect_stdout(io.StringIO()):
        GUARD.patch(root, apply=False)
    source = root / GUARD.SDK / 'tools/optimizer'
    inventory = {p.name for p in source.iterdir()}
    allowed = set(PINS['nativeSources']) | {'optimizer.cpp' + GUARD.BACKUP_SUFFIX}
    if inventory - allowed or not set(PINS['nativeSources']).issubset(inventory):
        raise ValueError('Optimizer source inventory differs from pinned eleven files')
    hashes = {}
    for name, original in PINS['nativeSources'].items():
        actual = sha(file(source / name))
        fixed = GUARD.SPECS[0]['after'] if name == 'optimizer.cpp' else original
        if actual not in ({fixed} if guarded else {original, fixed}):
            raise ValueError('Optimizer source fingerprint differs: ' + name)
        hashes[name] = actual
    fallback = sha(file(root / GUARD.SPECS[1]['path']))
    if guarded and fallback != GUARD.SPECS[1]['after']:
        raise ValueError('Fallback source is not guarded')
    return hashes, fallback


def toolchain(cmake=None):
    """Resolve an explicit VS2022/MSVC/SDK tuple; fingerprint executable inputs."""
    cmake = file(Path(cmake or shutil.which('cmake') or r'C:\Program Files\CMake\bin\cmake.exe'))
    vswhere = file(Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) /
                   'Microsoft Visual Studio/Installer/vswhere.exe')
    installations = json.loads(capture([vswhere, '-latest', '-products', '*', '-version', '[17.0,18.0)',
                                       '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-format', 'json']))
    if len(installations) != 1:
        raise ValueError('Expected one selected VS2022 C++ installation')
    install = installations[0]
    vs = GUARD.physical(Path(install['installationPath']))
    version_file = file(vs / 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt')
    version = version_file.read_text().strip()
    if not re.fullmatch(r'14\.\d+\.\d+', version):
        raise ValueError('Unexpected MSVC toolset version')
    compiler = vs / ('VC/Tools/MSVC/' + version + '/bin/Hostx64/x64')
    kits = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Windows Kits/10'
    versions = [p.name for p in (kits / 'Include').iterdir() if re.fullmatch(r'10\.0\.\d+\.\d+', p.name)]
    if not versions:
        raise ValueError('Windows 10 SDK required')
    sdk = max(versions, key=lambda v: tuple(map(int, v.split('.'))))
    inputs = [cmake, vswhere, version_file] + [compiler / n for n in ('cl.exe', 'link.exe', 'c1xx.dll', 'c2.dll')]
    inputs += [kits / ('Include/' + sdk + '/' + n) for n in ('um/Windows.h', 'ucrt/stdio.h', 'shared/sdkddkver.h')]
    inputs += [kits / ('Lib/' + sdk + '/' + n) for n in ('um/x64/kernel32.lib', 'ucrt/x64/ucrt.lib')]
    helper = compiler / 'vctip.exe'
    vctip = None
    if helper.exists():
        helper = file(helper)
        vctip = dict(path=str(helper), sha256=sha(helper))
        inputs.append(helper)
    return dict(cmake=str(cmake), cmakeVersion=capture([cmake, '--version']), vs=str(vs),
                installationVersion=install['installationVersion'], msvc=version, sdk=sdk, vctip=vctip,
                files={str(file(p)): sha(p) for p in inputs})


def verify_tools(identity):
    for path, expected in identity['toolchain']['files'].items():
        if sha(file(path)) != expected:
            raise ValueError('Native toolchain changed: ' + path)


def verify_executable(executable, node, fallback, output, env):
    proof = directory(output / ('proof-' + uuid.uuid4().hex))
    fixture, verifier = proof / 'input.js', proof / 'verify.cjs'
    fixture.write_text(PROBE)
    verifier.write_text(VERIFY)
    for label, argv in (
        ('native', [executable, fixture, 'asm', 'simplifyExpressions']),
        ('native-tail', [executable, fixture, 'asm', 'eliminate', 'simplifyExpressions', 'registerizeHarder', 'asmLastOpts']),
        ('fallback', [node, fallback, fixture, 'asm', 'simplifyExpressions'])):
        result = proof / (label + '.js')
        run(argv, proof, env, result, 30)
        log = proof / (label + '.verify.log')
        run([node, verifier, result], proof, env, log, 30)
        if log.read_text().strip() != 'OPTIMIZER_RHS_GUARD_PASS':
            raise ValueError('Missing actual optimizer regression proof')
    return str(proof)


def prepare(root, cmake=None):
    root = GUARD.validate_root(root)
    sources(root)  # all auxiliary inputs AND both guards checked before mutation
    tools = toolchain(cmake)
    compiler_clear()
    base = directory(root / 'Engine/Intermediate/BOpt')
    with lock(base / 'prepare.lock'):
        with contextlib.redirect_stdout(io.StringIO()):
            GUARD.patch(root, apply=True)
        source_hashes, fallback_hash = sources(root, guarded=True)
        identity = dict(schema=1, sources=source_hashes, fallback=fallback_hash, toolchain=tools,
                        recipe={k:PINS[k] for k in ('generator', 'architecture', 'configuration', 'workers', 'cmakePolicyMinimum', 'cxxStandard', 'cxxFlags')},
                        helper=sha(Path(__file__)), pins=sha(PIN_FILE), guard=sha(HERE / 'patch-browser-optimizer.py'),
                        regression=fingerprint([PROBE, VERIFY]))
        key = fingerprint(identity)
        cache = base / key[:16]
        exists = cache.exists()
        cache = directory(cache)
        executable = cache / 'build/Release/optimizer.exe'
        receipt = cache / 'verified.json'
        node = file(root / 'Engine/Extras/ThirdPartyNotUE/emsdk/Win64/node/4.1.1_64bit/bin/node.exe')
        env = dict(os.environ, TEMP=str(directory(cache / 'temp')), TMP=str(cache / 'temp'), PYTHONDONTWRITEBYTECODE='1')
        for name in ('CC', 'CXX', 'CFLAGS', 'CXXFLAGS', 'CPPFLAGS', 'LDFLAGS', 'CL', '_CL_', 'INCLUDE', 'LIB', 'LIBPATH'):
            env.pop(name, None)
        if exists:
            saved = json.loads(file(receipt).read_text())
            if saved.get('fingerprint') != key or saved.get('identity') != identity or sha(file(executable)) != saved.get('executableSha256'):
                raise ValueError('Incomplete/modified optimizer cache; inspect it before retrying: ' + str(cache))
        else:
            copied = directory(cache / 'source')
            for name in source_hashes:
                (copied / name).write_bytes(file(root / GUARD.SDK / 'tools/optimizer' / name).read_bytes())
            if {name: sha(file(copied / name)) for name in source_hashes} != source_hashes:
                raise ValueError('Source changed while copying optimizer inputs')
            configure = [tools['cmake'], '-S', str(copied), '-B', str(cache / 'build'),
                         '-G', PINS['generator'], '-A', PINS['architecture'], '-T', 'version=' + tools['msvc'],
                         '-DCMAKE_GENERATOR_INSTANCE=' + tools['vs'], '-DCMAKE_SYSTEM_VERSION=' + tools['sdk'],
                         '-DCMAKE_CXX_STANDARD=' + PINS['cxxStandard'], '-DCMAKE_CXX_FLAGS=' + PINS['cxxFlags'],
                         '-DCMAKE_POLICY_VERSION_MINIMUM=' + PINS['cmakePolicyMinimum']]
            build = [tools['cmake'], '--build', str(cache / 'build'), '--config', 'Release', '--parallel', '2', '--', '/nr:false']
            atomic_json(cache / 'build-plan.json', dict(identity=identity, configure=configure, build=build))
            run(configure, cache, env, cache / 'configure.log', survivor=tools['vctip'])
            run(build, cache, env, cache / 'build.log', survivor=tools['vctip'])
        proof = verify_executable(file(executable), node, file(root / GUARD.SPECS[1]['path']), cache, env)
        verify_tools(identity)
        if sources(root, guarded=True) != (source_hashes, fallback_hash):
            raise ValueError('Source changed during optimizer preparation')
        selection = dict(fingerprint=key, identity=identity, executable=str(executable),
                         executableSha256=sha(executable), proof=proof)
        atomic_json(receipt, selection)
        return dict(selection=str(receipt), **selection)


def selection(root, path):
    path = file(path)
    base = root / 'Engine/Intermediate/BOpt'
    if path.name != 'verified.json' or path.parent.parent != base:
        raise ValueError('Selection must be this checkout\'s verified cache receipt')
    saved = json.loads(path.read_text())
    identity = saved['identity']
    if (not re.fullmatch(r'[0-9a-f]{64}', saved['fingerprint'])
            or saved['fingerprint'][:16] != path.parent.name
            or fingerprint(identity) != saved['fingerprint']):
        raise ValueError('Optimizer fingerprint/receipt differs')
    if identity['helper'] != sha(Path(__file__)) or identity['pins'] != sha(PIN_FILE) or identity['guard'] != sha(HERE / 'patch-browser-optimizer.py'):
        raise ValueError('Preparation implementation changed; prepare again')
    if sources(root, guarded=True) != (identity['sources'], identity['fallback']):
        raise ValueError('Guarded source changed; prepare again')
    executable = file(path.parent / 'build/Release/optimizer.exe')
    if str(executable) != saved['executable'] or sha(executable) != saved['executableSha256']:
        raise ValueError('Selected executable changed')
    verify_tools(identity)
    return saved


def output_paths(root, configuration):
    if configuration not in ('Development', 'Shipping'):
        raise ValueError('Unsupported configuration')
    name = 'TournamentBrowser.js' if configuration == 'Development' else 'TournamentBrowser-HTML5-Shipping.js'
    folder = root / 'UnrealTournament/Binaries/HTML5'
    return [folder / name, folder / name.replace('.js', '.bc'), folder / (name + '.mem'), folder / (name + '.symbols')]


def validate_generation(outputs, log, selected):
    for path in outputs:
        if not file(path).stat().st_size:
            raise ValueError('Empty link output: ' + str(path))
    text = outputs[0].read_text(encoding='utf-8')
    for name in CONTROLS:
        if 'Module["_TournamentBrowser' + name + '"]' not in text:
            raise ValueError('Missing browser control export: ' + name)
    memory = re.search(r'\bmemoryInitializer\s*=\s*([\'\"])(.*?)\1', text)
    if not memory or memory.group(2) != outputs[2].name:
        raise ValueError('JavaScript does not reference the matching memory initializer')
    with outputs[1].open('rb') as stream:
        if stream.read(4) not in (b'BC\xc0\xde', b'\xde\xc0\x17\x0b'):
            raise ValueError('Expected fresh LLVM bitcode output')
    evidence = file(log).read_text(encoding='utf-8', errors='replace')
    if re.search(r'unresolved symbol:|undefined symbol:', evidence, re.I):
        raise ValueError('Unresolved browser symbols')
    if not re.search(r'^\s*\[\d+/\d+\].*\b' + re.escape(outputs[0].name) + r'\s*$', evidence, re.M):
        raise ValueError('UBT did not report a fresh JavaScript link action')
    # Windows may print mixed separators; compare normalized exact paths.
    normalized = evidence.replace('\\', '/')
    native_path = re.escape(selected['executable'].replace('\\', '/'))
    if not re.search(r'^DEBUG:root:env forcing native optimizer at ' + native_path + r'\s*$', normalized, re.M) or 'js optimizer using native' not in evidence:
        raise ValueError('Missing selected native executable invocation proof')
    if not re.search(r'applying js optimization passes:[^\r\n]*\bsimplifyExpressions\b', evidence):
        raise ValueError('Guarded simplifyExpressions pass was not run')
    return {p.name:sha(p) for p in outputs}


def link(root, selected_path, configuration='Development', workers=2):
    root = GUARD.validate_root(root)
    selected = selection(root, selected_path)
    compiler_clear()
    if not 1 <= workers <= 8:
        raise ValueError('Workers must be 1..8')
    base = directory(root / 'Engine/Intermediate/BOpt')
    outputs = output_paths(root, configuration)
    directory(outputs[0].parent)
    ubt = file(root / 'Engine/Binaries/DotNET/UnrealBuildTool.exe')
    current = base / ('last-' + configuration + '.json')
    log = root / 'UnrealTournament/Saved/Logs/BrowserPort/compile.log'
    directory(log.parent)
    for path in [*outputs, current, log]:
        GUARD.physical(path, missing_leaf=True)
    with lock(base / 'engine-link.lock') as lease:
        backup = directory(base / ('generation-' + uuid.uuid4().hex))
        moved = []
        before = {str(p):sha(p) for p in [*outputs, current, log] if p.exists()}
        atomic_json(backup / 'before.json', dict(files=before, completeArtifactSet=all(p.exists() for p in outputs)))
        try:
            for path in [*outputs, current, log]:
                if path.exists():
                    destination = backup / path.name
                    os.replace(path, destination)
                    moved.append((path, destination))
        except BaseException:
            for path, destination in reversed(moved):
                if not path.exists():
                    os.replace(destination, path)
            raise
        # Output absence, actual link execution, and a coherent receipt establish
        # provenance. Timestamps/hash inequality alone are deliberately not proof.
        env = dict(os.environ, EMSCRIPTEN_NATIVE_OPTIMIZER=selected['executable'], EMCC_NATIVE_OPTIMIZER='2',
                   EMCC_CORES=str(workers), EMCC_DEBUG='1', TOURNAMENT_UT4_UCRT_VERSION='10.0.10240.0',
                   PYTHONDONTWRITEBYTECODE='1')
        env.pop('EMCC_JSOPT_BLACKLIST', None)
        env.pop('EMCC_DEBUG_SAVE', None)
        argv = [ubt, 'TournamentBrowser', 'HTML5', configuration,
                '-Project=' + str(root / 'UnrealTournament/UnrealTournament.uproject'),
                '-NoUBTMakefiles', '-NoHotReload', '-2015']
        try:
            run(argv, root / 'Engine/Source', env, log, 7200)
            hashes = validate_generation(outputs, log, selected)
            if selection(root, selected_path) != selected:
                raise ValueError('Optimizer selection changed during link')
            receipt = dict(schema=1, configuration=configuration, optimizerFingerprint=selected['fingerprint'],
                           executable=selected['executable'], executableSha256=selected['executableSha256'],
                           outputs=hashes, compileLogSha256=sha(log), command=list(map(str, argv)), previous=str(backup))
            atomic_json(current, receipt)
            return receipt
        except BaseException as error:
            # Signal restoration can wrap a drain failure in KeyboardInterrupt.
            # Live targets must remain in place even if the outer type changes.
            if lease.unsafe or has_undrained_error(error):
                raise
            # Keep the original exception even if evidence cleanup also fails.
            try:
                failed = directory(backup / 'failed')
                for path in [*outputs, current]:
                    if path.exists():
                        file(path)
                        os.replace(path, failed / path.name)
            except (OSError, ValueError) as cleanup:
                print('Failed-generation quarantine error: ' + str(cleanup), file=sys.stderr)
            raise
        finally:
            # No os.environ mutation anywhere: parent values/presence survive all
            # prepare, compiler, validation, and cleanup failures unchanged.
            env.clear()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root', type=Path)
    commands = parser.add_subparsers(dest='mode', required=True)
    prepare_args = commands.add_parser('prepare')
    prepare_args.add_argument('--cmake')
    link_args = commands.add_parser('link')
    link_args.add_argument('--selection', required=True, type=Path)
    link_args.add_argument('--configuration', choices=['Development', 'Shipping'], default='Development')
    link_args.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    try:
        result = prepare(args.source_root, args.cmake) if args.mode == 'prepare' else link(args.source_root, args.selection, args.configuration, args.workers)
        print(json.dumps(result))
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
