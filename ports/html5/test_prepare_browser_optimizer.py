"""Original, local-only fixtures; no SDK, licensed inputs, Windows or native build.

python3 -B ports/html5/test_prepare_browser_optimizer.py -v
Filesystem guards and generation transactions execute against temporary files.
Compiler/optimizer processes are mocked; these are not native/gameplay proofs.
"""
import contextlib
import copy
import ctypes
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location('prepare_optimizer', Path(__file__).with_name('prepare-browser-optimizer.py'))
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)
REAL_RUN = P.run


@contextlib.contextmanager
def signal_on_restoration(number):
    """Actual SIGINT at a selected restored-handler generator return."""
    previous = sys.gettrace()
    hits = []
    def trace(frame, event, arg):
        if (frame.f_code is P.ignore_interrupts.__wrapped__.__code__ and event == 'return'
                and signal.getsignal(signal.SIGINT) != signal.SIG_IGN):
            hits.append(True)
            if len(hits) == number:
                signal.raise_signal(signal.SIGINT)
        return trace
    try:
        sys.settrace(trace)
        yield hits
    finally:
        sys.settrace(previous)


@contextlib.contextmanager
def cleanup_entry_probe(root, target):
    """Real owned descendants; SIGINT prevents entry into termination itself.

    The yielded state permits assertions while writers may still exist. Fixture
    exit explicitly terminates/drains only its captured tree, even on failures.
    """
    ready, trigger = root / 'entry-ready', root / 'entry-trigger'
    child, parent = root / 'entry-child.py', root / 'entry-parent.py'
    child.write_text("import pathlib,time,sys\nout,ready,trigger=map(pathlib.Path,sys.argv[1:])\nout.write_text('live partial')\nready.touch()\nend=time.monotonic()+10\nwhile not trigger.exists() and time.monotonic()<end: time.sleep(.01)\nif trigger.exists(): out.write_text('live late write')\n")
    parent.write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable]+sys.argv[1:])\ntime.sleep(20)\n")
    argv = [sys.executable, parent, child, target, ready, trigger]
    primary = subprocess.TimeoutExpired(list(map(str, argv)), 1)
    original_tree, original_wait = P.ProcessTree, P.wait_tree
    original_trace = sys.gettrace()
    captures, hits = [], []
    entry_line = next(index for index, line in enumerate(Path(P.__file__).read_text().splitlines(), 1)
                      if line.strip() == 'previous = signal.signal(signal.SIGINT, signal.SIG_IGN)')
    def factory(*args):
        tree = original_tree(*args)
        terminate, close = tree.terminate, tree.close
        tree.terminate, tree.close = mock.Mock(wraps=terminate), mock.Mock(wraps=close)
        captures.append((tree, terminate, close))
        return tree
    def fail_wait(tree, argv, timeout):
        deadline = time.monotonic() + 5
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        if not ready.exists():
            raise AssertionError('actual descendant did not become ready')
        raise primary
    def trace(frame, event, arg):
        if (event == 'line' and frame.f_code is P.ignore_interrupts.__wrapped__.__code__
                and frame.f_lineno == entry_line):
            hits.append(True)
            if len(hits) == 2:
                signal.raise_signal(signal.SIGINT)
        return trace
    try:
        with mock.patch.object(P, 'ProcessTree', side_effect=factory), mock.patch.object(P, 'monitor_command', side_effect=fail_wait):
            sys.settrace(trace)
            yield dict(argv=argv, primary=primary, captures=captures, hits=hits,
                       target=target, ready=ready, trigger=trigger)
    finally:
        sys.settrace(original_trace)
        for tree, terminate, close in captures:
            with P.ignore_interrupts():
                try:
                    terminate()
                    original_wait(tree, list(map(str, argv)), 5)
                finally:
                    close()


def prove_live_writer(probe):
    """Used only while ownership remains unsafe/locked, never as successful drain."""
    probe['trigger'].touch()
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if probe['target'].exists() and probe['target'].read_text() == 'live late write':
            return True
        time.sleep(.01)
    return False


class Fixture(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='optimizer-integration-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.specs = []
        self.pin = copy.deepcopy(P.PINS)
        for index, spec in enumerate(P.GUARD.SPECS):
            data = b'// original synthetic input\r\n    if (eligible) {\r\n        observe();\r\n    }\r\n'
            fixed = data.replace(b'if (', b'if (' + spec['guard'])
            self.specs.append({**spec, 'line': 2, 'before': P.GUARD.digest(data), 'after': P.GUARD.digest(fixed)})
            self.put(spec['path'], data)
        self.stack.enter_context(mock.patch.object(P.GUARD, 'SPECS', tuple(self.specs)))
        for name in self.pin['nativeSources']:
            path = self.root / P.GUARD.SDK / 'tools/optimizer' / name
            if not path.exists():
                path.write_text('// synthetic ' + name)
            self.pin['nativeSources'][name] = P.sha(path)
        self.stack.enter_context(mock.patch.object(P, 'PINS', self.pin))
        self.put('.tournament-browser-port', b'')
        self.put('Engine/Build/Build.version', json.dumps(dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)).encode())
        self.put(str(P.GUARD.SDK / 'emscripten-version.txt'), b'"1.36.13"')
        self.put('Engine/Extras/ThirdPartyNotUE/emsdk/Win64/node/4.1.1_64bit/bin/node.exe', b'fixture-node')
        self.put('Engine/Binaries/DotNET/UnrealBuildTool.exe', b'fixture-ubt')
        self.put('Engine/Source/placeholder', b'')
        self.tool = self.put('tools/cmake.exe', b'fixture-tool')
        self.vctip = self.put('tools/vctip.exe', b'fixture-telemetry-helper')
        self.tools = dict(cmake=str(self.tool), cmakeVersion='fixture-cmake', vs=str(self.root / 'tools'),
                          msvc='14.44.35207', sdk='10.0.26100.0',
                          vctip=dict(path=str(self.vctip), sha256=P.sha(self.vctip)),
                          files={str(self.tool):P.sha(self.tool), str(self.vctip):P.sha(self.vctip)})
        self.stack.enter_context(mock.patch.object(P, 'toolchain', return_value=self.tools))
        self.clear = self.stack.enter_context(mock.patch.object(P, 'compiler_clear'))
        self.calls = []
        self.policies = []
        self.runner = self.stack.enter_context(mock.patch.object(P, 'run', side_effect=self.build))
        self.proof = self.stack.enter_context(mock.patch.object(P, 'verify_executable', return_value='fixture-only-proof'))

    def put(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def build(self, argv, cwd, env, log, timeout=600, survivor=None):
        self.policies.append(survivor)
        self.calls.append((list(map(str, argv)), dict(env)))
        log.write_text('fixture compiler, no actual execution')
        if '--build' in argv:
            path = cwd / 'build/Release/optimizer.exe'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture-executable')

    def prepared(self):
        result = P.prepare(self.root)
        self.selected_path = Path(result.pop('selection'))
        self.selected = result
        return result

    def outputs(self):
        return P.output_paths(self.root, 'Development')

    def good_generation(self, argv, cwd, env, log, timeout):
        self.link_env = dict(env)
        outputs = self.outputs()
        for path in outputs:
            self.assertFalse(path.exists(), 'old artifact leaked into fresh link')
        outputs[0].write_text('var memoryInitializer = "' + outputs[2].name + '";\n' +
                             '\n'.join('Module["_TournamentBrowser' + name + '"]=function(){};' for name in P.CONTROLS))
        outputs[1].write_bytes(b'BC\xc0\xdeFixture')
        outputs[2].write_bytes(b'fixture-memory')
        outputs[3].write_bytes(b'0:_TournamentBrowserReady')
        log.write_text('[1/1] ' + outputs[0].name + '\nDEBUG:root:env forcing native optimizer at ' +
                       self.selected['executable'] + '\nDEBUG:root:js optimizer using native\n' +
                       'DEBUG:root:applying js optimization passes: asm eliminate simplifyExpressions emitJSON\n')

    def seed_old(self):
        for path in self.outputs():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('old ' + path.name).encode())
        base = self.root / 'Engine/Intermediate/BOpt'
        (base / 'last-Development.json').write_text('{"previous":"receipt"}')
        return {p.name:p.read_bytes() for p in self.outputs()}

    def link(self, runner=None):
        self.runner.side_effect = runner or self.good_generation
        return P.link(self.root, self.selected_path, workers=4)

    def generations(self):
        return list((self.root / 'Engine/Intermediate/BOpt').glob('generation-*'))


class PreparationTests(Fixture):
    def test_prepare_recipe_cache_and_actual_file_selection(self):
        result = self.prepared()
        configure = self.calls[0][0]
        for flag in ('-DCMAKE_CXX_STANDARD=14', '-DCMAKE_CXX_FLAGS=/FIfunctional', '-DCMAKE_POLICY_VERSION_MINIMUM=3.5'):
            self.assertIn(flag, configure)
        self.assertIn('Visual Studio 17 2022', configure)
        self.assertEqual(self.calls[1][0][-4:], ['--parallel', '2', '--', '/nr:false'])
        self.assertEqual(P.selection(self.root, self.selected_path), result)
        self.assertEqual(P.prepare(self.root)['fingerprint'], result['fingerprint'])
        self.assertEqual(len(self.calls), 2, 'cached preparation unexpectedly compiled')
        self.assertEqual(self.proof.call_count, 2, 'reuse must rerun semantic checks')
        self.assertEqual(len(result['identity']['sources']), 11)
        self.assertEqual(self.policies, [self.tools['vctip'], self.tools['vctip']])
        self.assertEqual(result['identity']['toolchain']['vctip']['sha256'], P.sha(self.vctip))

    def test_short_cache_keeps_full_identity_and_old_layout_untouched(self):
        old = self.put('Engine/Intermediate/BrowserOptimizer/old-failed-cache/evidence.json', b'old evidence')
        result = self.prepared()
        self.assertEqual(len(self.selected_path.parent.name), 16)
        self.assertEqual(len(result['fingerprint']), 64)
        self.assertEqual(self.selected_path.parent.name, result['fingerprint'][:16])
        self.assertEqual(P.fingerprint(result['identity']), result['fingerprint'])
        self.assertEqual(old.read_bytes(), b'old evidence')

    def test_prefix_collision_cannot_reuse_or_select_another_full_identity(self):
        self.prepared()
        saved = json.loads(self.selected_path.read_text())
        collision = copy.deepcopy(saved)
        collision['fingerprint'] = saved['fingerprint'][:16] + ('0' if saved['fingerprint'][16] != '0' else '1') + saved['fingerprint'][17:]
        self.selected_path.write_text(json.dumps(collision))
        before = self.selected_path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'modified optimizer cache'):
            P.prepare(self.root)
        with self.assertRaisesRegex(ValueError, 'fingerprint/receipt differs'):
            P.selection(self.root, self.selected_path)
        self.assertEqual(before, self.selected_path.read_bytes())
        self.assertEqual(len(self.calls), 2, 'collision triggered build or overwrite')

    def test_second_source_and_auxiliary_pin_checked_before_any_patch(self):
        for relative in (P.GUARD.SPECS[1]['path'], P.GUARD.SDK / 'tools/optimizer/parser.h'):
            with self.subTest(path=relative):
                path = self.root / relative
                old = path.read_bytes()
                path.write_bytes(old + b'changed')
                with self.assertRaises(ValueError):
                    P.prepare(self.root)
                self.assertFalse(Path(str(self.root / P.GUARD.SPECS[0]['path']) + P.GUARD.BACKUP_SUFFIX).exists())
                self.assertFalse(self.calls)
                path.write_bytes(old)

    def test_active_compiler_blocks_source_writes(self):
        self.clear.side_effect = RuntimeError('compiler active')
        with self.assertRaisesRegex(RuntimeError, 'compiler active'):
            P.prepare(self.root)
        self.assertFalse(Path(str(self.root / P.GUARD.SPECS[0]['path']) + P.GUARD.BACKUP_SUFFIX).exists())

    def test_modified_cached_executable_and_missing_receipt_rejected(self):
        self.prepared()
        exe = Path(self.selected['executable'])
        old = exe.read_bytes()
        exe.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'modified optimizer cache'):
            P.prepare(self.root)
        exe.write_bytes(old)
        self.selected_path.unlink()
        with self.assertRaises((OSError, ValueError)):
            P.prepare(self.root)
        self.assertEqual(len(self.calls), 2)

    def test_toolchain_change_selects_new_fingerprint(self):
        first = self.prepared()['fingerprint']
        self.tool.write_bytes(b'new version')
        self.tools['files'][str(self.tool)] = P.sha(self.tool)
        self.assertNotEqual(P.prepare(self.root)['fingerprint'], first)
        self.assertEqual(len(self.calls), 4)

    def test_build_failure_has_no_verified_receipt_or_parent_env_changes(self):
        with mock.patch.dict(os.environ, {'CXXFLAGS':'parent-flags', 'CL':'parent-cl', 'EMCC_NATIVE_OPTIMIZER':'0'}):
            before = dict(os.environ)
            self.runner.side_effect = RuntimeError('compile failed')
            with self.assertRaisesRegex(RuntimeError, 'compile failed'):
                P.prepare(self.root)
            self.assertEqual(dict(os.environ), before)
        self.assertFalse(list(self.root.rglob('verified.json')))
        self.assertFalse(list(self.root.rglob('*.lock')))

    def test_failed_semantic_proof_never_marks_cache_verified(self):
        self.proof.side_effect = ValueError('semantic mismatch')
        with self.assertRaisesRegex(ValueError, 'semantic mismatch'):
            P.prepare(self.root)
        self.assertFalse(list(self.root.rglob('verified.json')))

    def test_selection_rejects_tool_and_guard_drift(self):
        self.prepared()
        self.tool.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'toolchain changed'):
            P.selection(self.root, self.selected_path)
        self.tool.write_bytes(b'fixture-tool')
        (self.root / P.GUARD.SPECS[1]['path']).write_bytes(b'changed')
        with self.assertRaises(ValueError):
            P.selection(self.root, self.selected_path)

    def test_cache_hardlink_refused(self):
        self.prepared()
        os.link(self.selected['executable'], self.root / 'alias')
        with self.assertRaisesRegex(ValueError, 'shared file'):
            P.selection(self.root, self.selected_path)


class LinkTests(Fixture):
    def setUp(self):
        super().setUp()
        self.prepared()

    def test_fresh_link_backs_up_quartet_and_records_hashes(self):
        old = self.seed_old()
        result = self.link()
        backup = Path(result['previous'])
        for name, data in old.items():
            self.assertEqual((backup / name).read_bytes(), data)
        self.assertTrue(json.loads((backup / 'before.json').read_text())['completeArtifactSet'])
        self.assertEqual(result['outputs'], {p.name:P.sha(p) for p in self.outputs()})
        # Matching tool receipt still forces a second fresh generation.
        self.link()
        self.assertEqual(len(self.generations()), 2)

    def test_child_overrides_and_parent_environment_success_and_failure(self):
        with mock.patch.dict(os.environ, {'EMSCRIPTEN_NATIVE_OPTIMIZER':'parent-exe', 'EMCC_NATIVE_OPTIMIZER':'0',
                                         'EMCC_JSOPT_BLACKLIST':'simplifyExpressions', 'EMCC_CORES':'8',
                                         'EMCC_DEBUG':'0', 'EMCC_DEBUG_SAVE':'1', 'TOURNAMENT_UT4_UCRT_VERSION':'other'}):
            before = dict(os.environ)
            self.link()
            self.assertEqual(dict(os.environ), before)
            self.assertEqual(self.link_env['EMSCRIPTEN_NATIVE_OPTIMIZER'], self.selected['executable'])
            self.assertEqual(self.link_env['EMCC_NATIVE_OPTIMIZER'], '2')
            self.assertEqual(self.link_env['EMCC_CORES'], '4')
            self.assertEqual(self.link_env['EMCC_DEBUG'], '1')
            self.assertNotIn('EMCC_JSOPT_BLACKLIST', self.link_env)
            self.assertNotIn('EMCC_DEBUG_SAVE', self.link_env)
            with self.assertRaisesRegex(RuntimeError, 'link failed'):
                self.link(lambda *a: (_ for _ in ()).throw(RuntimeError('link failed')))
            self.assertEqual(dict(os.environ), before)

    def test_zero_exit_up_to_date_is_failure_not_reused_old_outputs(self):
        old = self.seed_old()
        def no_link(argv, cwd, env, log, timeout):
            log.write_text('Target is up to date')
        with self.assertRaises((OSError, ValueError)):
            self.link(no_link)
        for path in self.outputs():
            self.assertFalse(path.exists())
            self.assertEqual((self.generations()[0] / path.name).read_bytes(), old[path.name])

    def test_partial_failed_output_quarantined_and_original_preserved(self):
        old = self.seed_old()
        def fail(argv, cwd, env, log, timeout):
            self.outputs()[0].write_bytes(b'partial')
            log.write_text('failed')
            raise RuntimeError('primary build error')
        with self.assertRaisesRegex(RuntimeError, 'primary build error'):
            self.link(fail)
        backup = self.generations()[0]
        self.assertEqual((backup / 'failed' / self.outputs()[0].name).read_bytes(), b'partial')
        for name, data in old.items():
            self.assertEqual((backup / name).read_bytes(), data)
        self.assertFalse(list(self.root.rglob('*.lock')))

    def test_validation_rejects_near_misses_and_missing_artifacts(self):
        def mutate(kind):
            def runner(*args):
                self.good_generation(*args)
                js, bc, mem, symbols = self.outputs()
                log = args[3]
                if kind == 'wrong-exe':
                    log.write_text(log.read_text().replace(self.selected['executable'], self.selected['executable'] + '.evil'))
                elif kind == 'blacklisted-pass':
                    log.write_text(log.read_text().replace('simplifyExpressions', 'eliminate'))
                elif kind == 'no-link-action':
                    log.write_text(log.read_text().replace('[1/1]', 'cached'))
                elif kind == 'memory-reference':
                    js.write_text(js.read_text().replace(mem.name, 'stale.mem'))
                elif kind == 'export':
                    js.write_text(js.read_text().replace('_TournamentBrowserReady', '_unrelated'))
                elif kind == 'bitcode':
                    bc.write_bytes(b'not-bitcode')
                elif kind == 'symbols':
                    symbols.unlink()
                elif kind == 'unresolved':
                    log.write_text(log.read_text() + 'undefined symbol: broken\n')
            return runner
        for kind in ('wrong-exe', 'blacklisted-pass', 'no-link-action', 'memory-reference', 'export', 'bitcode', 'symbols', 'unresolved'):
            with self.subTest(kind=kind), self.assertRaises((ValueError, OSError)):
                self.link(mutate(kind))
            self.assertFalse(any(p.exists() for p in self.outputs()))

    def test_selection_drift_during_link_invalidates_new_generation(self):
        def drift(*args):
            self.good_generation(*args)
            Path(self.selected['executable']).write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'executable changed'):
            self.link(drift)
        self.assertFalse(any(p.exists() for p in self.outputs()))

    def test_backup_move_failure_rolls_back_before_ubt(self):
        old = self.seed_old()
        original = os.replace
        def fail_second(source, target):
            if Path(source) == self.outputs()[1]:
                raise OSError('backup failed')
            return original(source, target)
        with mock.patch.object(P.os, 'replace', side_effect=fail_second), self.assertRaisesRegex(OSError, 'backup failed'):
            self.link()
        for path in self.outputs():
            self.assertEqual(path.read_bytes(), old[path.name])
        self.assertEqual(len(self.calls), 2, 'UBT ran after failed backup')

    def test_missing_ubt_does_not_move_outputs(self):
        old = self.seed_old()
        (self.root / 'Engine/Binaries/DotNET/UnrealBuildTool.exe').unlink()
        with self.assertRaises((OSError, ValueError)):
            self.link()
        self.assertFalse(self.generations())
        for path in self.outputs():
            self.assertEqual(path.read_bytes(), old[path.name])

    def test_primary_exception_survives_failed_quarantine(self):
        original = os.replace
        def move(source, target):
            if Path(target).parent.name == 'failed':
                raise OSError('quarantine failed')
            return original(source, target)
        def fail(argv, cwd, env, log, timeout):
            self.outputs()[0].write_bytes(b'partial')
            raise RuntimeError('primary error')
        with mock.patch.object(P.os, 'replace', side_effect=move), contextlib.redirect_stderr(io.StringIO()) as err:
            with self.assertRaisesRegex(RuntimeError, 'primary error'):
                self.link(fail)
        self.assertIn('quarantine failed', err.getvalue())
        self.assertFalse((self.root / 'Engine/Intermediate/BOpt/last-Development.json').exists())

    def test_undrained_tree_keeps_lock_and_does_not_quarantine_live_targets(self):
        self.seed_old()
        def fail(argv, cwd, env, log, timeout):
            self.outputs()[0].write_bytes(b'possibly still being written')
            raise P.UndrainedProcessError('fixture owned tree still active')
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(P.UndrainedProcessError):
            self.link(fail)
        self.assertEqual(self.outputs()[0].read_bytes(), b'possibly still being written')
        self.assertTrue((self.root / 'Engine/Intermediate/BOpt/engine-link.lock').exists())
        self.assertFalse((self.generations()[0] / 'failed').exists())

    def test_actual_descendant_cannot_recreate_quartet_after_quarantine(self):
        old = self.seed_old()
        ready, trigger = self.root / 'ready', self.root / 'trigger'
        child = self.put('child.py', b'')
        child.write_text("import pathlib,time,sys\noutput,ready,trigger=map(pathlib.Path,sys.argv[1:])\noutput.write_text('partial')\nready.touch()\nend=time.monotonic()+10\nwhile not trigger.exists() and time.monotonic()<end: time.sleep(.01)\nif trigger.exists(): output.write_text('LATE WRITE')\n")
        parent = self.put('parent.py', b'')
        parent.write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable]+sys.argv[1:])\ntime.sleep(20)\n")
        def actual_runner(argv, cwd, env, log, timeout):
            REAL_RUN([sys.executable, parent, child, self.outputs()[0], ready, trigger], self.root, env, log, timeout=1)
        with self.assertRaises(subprocess.TimeoutExpired):
            self.link(actual_runner)
        self.assertTrue(ready.exists(), 'no actual descendant was started')
        backup = self.generations()[0]
        self.assertEqual((backup / 'failed' / self.outputs()[0].name).read_text(), 'partial')
        self.assertFalse((backup.parent / 'engine-link.lock').exists())
        trigger.touch()
        time.sleep(.25)
        self.assertFalse(any(p.exists() for p in self.outputs()), 'writer recreated output after quarantine/unlock')
        for name, data in old.items():
            self.assertEqual((backup / name).read_bytes(), data)

    def test_cleanup_restore_sigint_keeps_link_lock_and_live_paths(self):
        old = self.seed_old()
        tree = mock.Mock()
        tree.terminate.side_effect = OSError('injected termination failure')
        primary = subprocess.TimeoutExpired(['fixture'], 1)
        def runner(argv, cwd, env, log, timeout):
            self.outputs()[0].write_bytes(b'live target')
            REAL_RUN(['fixture'], cwd, env, log, timeout=1)
        with mock.patch.object(P, 'ProcessTree', return_value=tree), mock.patch.object(P, 'monitor_command', side_effect=primary):
            with contextlib.redirect_stderr(io.StringIO()), signal_on_restoration(2) as hits:
                with self.assertRaises(KeyboardInterrupt) as caught:
                    self.link(runner)
        self.assertEqual(len(hits), 2)
        self.assertIsInstance(caught.exception.__context__, P.UndrainedProcessError)
        self.assertIs(caught.exception.__context__.__cause__, primary)
        self.assertTrue((self.root / 'Engine/Intermediate/BOpt/engine-link.lock').exists())
        self.assertEqual(self.outputs()[0].read_bytes(), b'live target')
        self.assertFalse((self.generations()[0] / 'failed').exists())
        for name, data in old.items():
            self.assertEqual((self.generations()[0] / name).read_bytes(), data)

    def test_real_cleanup_entry_sigint_retains_link_lease_and_live_paths(self):
        old = self.seed_old()
        leases = []
        with cleanup_entry_probe(self.root, self.outputs()[0]) as probe:
            def runner(argv, cwd, env, log, timeout):
                leases.append(P.ACTIVE_LOCKS.get()[-1])
                REAL_RUN(probe['argv'], self.root, env, log, timeout=1)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(KeyboardInterrupt) as caught:
                self.link(runner)
            self.assertIs(caught.exception.__context__, probe['primary'])
            self.assertFalse(P.has_undrained_error(caught.exception), 'state must work without exception marker')
            self.assertTrue(leases[0].unsafe)
            self.assertEqual(len(leases[0].writers), 1)
            tree = probe['captures'][0][0]
            self.assertIs(leases[0].writers[0].tree, tree)
            tree.terminate.assert_not_called()
            tree.close.assert_not_called()
            self.assertTrue((self.root / 'Engine/Intermediate/BOpt/engine-link.lock').exists())
            self.assertEqual(self.outputs()[0].read_text(), 'live partial')
            self.assertFalse((self.generations()[0] / 'failed').exists())
            self.assertTrue(prove_live_writer(probe), 'probe must demonstrate real surviving writer')
            self.assertTrue(leases[0].unsafe)
            self.assertFalse(P.ACTIVE_LOCKS.get(), 'unwound lease leaked into unrelated operation')
            for name, data in old.items():
                self.assertEqual((self.generations()[0] / name).read_bytes(), data)

    def test_shipping_names(self):
        self.assertEqual([p.name for p in P.output_paths(self.root, 'Shipping')],
                         ['TournamentBrowser-HTML5-Shipping.js', 'TournamentBrowser-HTML5-Shipping.bc',
                          'TournamentBrowser-HTML5-Shipping.js.mem', 'TournamentBrowser-HTML5-Shipping.js.symbols'])


class ProcessTreeTests(unittest.TestCase):
    """Real disposable processes, including a child outliving its direct parent.

    Same tests use Windows Job Objects when run on Windows; POSIX sessions here.
    No compiler, SDK, engine, network, or licensed input is used.
    """
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='optimizer-process-tree-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.ready = self.root / 'child-ready'
        self.trigger = self.root / 'write-now'
        self.output = self.root / 'descendant-output'
        self.child = self.root / 'child.py'
        self.parent = self.root / 'parent.py'
        self.child.write_text("import pathlib,time,sys\nr=pathlib.Path(sys.argv[1])\n(r/'child-ready').write_text('ready')\nend=time.monotonic()+10\nwhile not (r/'write-now').exists() and time.monotonic()<end: time.sleep(.01)\nif (r/'write-now').exists(): (r/'descendant-output').write_text('late write')\n")
        self.parent.write_text("import subprocess,sys,time\nsubprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]])\ntime.sleep(20)\n")
        self.argv = [sys.executable, str(self.parent), str(self.child), str(self.root)]

    def assert_no_late_write(self):
        self.assertTrue(self.ready.exists(), 'test did not actually start descendant')
        self.assertFalse(self.output.exists())
        # A surviving child has explicit permission to write AFTER run returned.
        self.trigger.touch()
        time.sleep(.25)
        self.assertFalse(self.output.exists(), 'descendant wrote after run returned')

    def test_timeout_drains_actual_descendant_before_return_and_unlock(self):
        lock = self.root / 'engine-link.lock'
        with self.assertRaises(subprocess.TimeoutExpired):
            with P.lock(lock):
                P.run(self.argv, self.root, dict(os.environ), self.root / 'log', timeout=1)
        self.assertFalse(lock.exists())
        self.assert_no_late_write()

    def test_failed_primary_drains_descendant_promptly_preserving_code_and_audit(self):
        self.parent.write_text("import pathlib,subprocess,sys,time\nr=pathlib.Path(sys.argv[2])\nsubprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]])\nend=time.monotonic()+5\nwhile not (r/'child-ready').exists() and time.monotonic()<end: time.sleep(.01)\nprint('primary failure',flush=True)\nsys.exit(7)\n")
        lock = self.root / 'engine-link.lock'
        started = time.monotonic()
        with self.assertRaises(subprocess.CalledProcessError) as caught:
            with P.lock(lock) as lease:
                P.run(self.argv, self.root, dict(os.environ), self.root / 'log', timeout=10)
        self.assertEqual(caught.exception.returncode, 7)
        self.assertLess(time.monotonic() - started, 5, 'waited for helper timeout after known failure')
        self.assertFalse(lock.exists())
        self.assertFalse(lease.unsafe)
        audit = json.loads((self.root / 'log.process.json').read_text())
        self.assertEqual(audit['primaryExit'], 7)
        self.assertEqual(audit['finalParentExit'], 7)
        self.assertTrue(audit['drained'])
        self.assertEqual((self.root / 'log').read_text().strip(), 'primary failure')
        self.assert_no_late_write()

    def test_pure_wait_does_not_raise_again_for_failed_primary(self):
        tree = mock.Mock()
        tree.active.return_value = False
        tree.process.wait.return_value = 7
        self.assertEqual(P.wait_tree(tree, ['fixture'], 0), 7)

    def test_success_waits_for_descendant_after_immediate_parent_exit(self):
        self.child.write_text("import pathlib,time,sys\nr=pathlib.Path(sys.argv[1])\ntime.sleep(.25)\n(r/'descendant-output').write_text('finished')\n")
        self.parent.write_text("import subprocess,sys\nsubprocess.Popen([sys.executable,sys.argv[1],sys.argv[2]])\n")
        P.run(self.argv, self.root, dict(os.environ), self.root / 'log', timeout=5)
        self.assertEqual(self.output.read_text(), 'finished')

    def test_interrupt_drains_actual_descendant_before_reraising(self):
        original = P.monitor_command
        calls = []
        def interrupt(tree, argv, timeout):
            calls.append(1)
            if len(calls) == 1:
                deadline = time.monotonic() + 5
                while not self.ready.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(self.ready.exists())
                raise KeyboardInterrupt('fixture interrupt')
            return original(tree, argv, timeout)
        lock = self.root / 'engine-link.lock'
        with mock.patch.object(P, 'monitor_command', side_effect=interrupt), self.assertRaises(KeyboardInterrupt):
            with P.lock(lock):
                P.run(self.argv, self.root, dict(os.environ), self.root / 'log', timeout=5)
        self.assertFalse(lock.exists())
        self.assert_no_late_write()

    def test_unconfirmed_drain_keeps_lock_and_original_cause(self):
        tree = mock.Mock()
        tree.terminate.side_effect = OSError('tree accounting unavailable')
        primary = subprocess.TimeoutExpired(['fixture'], 1)
        lock = self.root / 'engine-link.lock'
        with mock.patch.object(P, 'ProcessTree', return_value=tree), mock.patch.object(P, 'monitor_command', side_effect=primary):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(P.UndrainedProcessError) as caught:
                with P.lock(lock):
                    P.run(['fixture'], self.root, dict(os.environ), self.root / 'log', timeout=1)
        self.assertIs(caught.exception.__cause__, primary)
        self.assertTrue(lock.exists())
        tree.close.assert_called_once()

    def test_cleanup_restore_sigint_preserves_undrained_lock(self):
        tree = mock.Mock()
        tree.terminate.side_effect = OSError('injected termination failure')
        primary = subprocess.TimeoutExpired(['fixture'], 1)
        lock = self.root / 'engine-link.lock'
        with mock.patch.object(P, 'ProcessTree', return_value=tree), mock.patch.object(P, 'monitor_command', side_effect=primary):
            with contextlib.redirect_stderr(io.StringIO()), signal_on_restoration(2) as hits:
                with self.assertRaises(KeyboardInterrupt) as caught:
                    with P.lock(lock):
                        P.run(['fixture'], self.root, dict(os.environ), self.root / 'log', timeout=1)
        self.assertEqual(len(hits), 2)
        self.assertIsInstance(caught.exception.__context__, P.UndrainedProcessError)
        self.assertIs(caught.exception.__context__.__cause__, primary)
        self.assertTrue(lock.exists())
        tree.close.assert_called_once()

    def test_real_cleanup_entry_sigint_preserves_unsafe_token_without_marker(self):
        lock = self.root / 'engine-link.lock'
        with cleanup_entry_probe(self.root, self.output) as probe:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(KeyboardInterrupt) as caught:
                with P.lock(lock) as lease:
                    P.run(probe['argv'], self.root, dict(os.environ), self.root / 'log', timeout=1)
            self.assertIs(caught.exception.__context__, probe['primary'])
            self.assertFalse(P.has_undrained_error(caught.exception))
            self.assertEqual(len(probe['hits']), 2)
            self.assertTrue(lock.exists())
            self.assertTrue(lease.unsafe)
            self.assertFalse(lease.writers[0].drained)
            tree = probe['captures'][0][0]
            self.assertIs(lease.writers[0].tree, tree)
            tree.terminate.assert_not_called()
            tree.close.assert_not_called()
            self.assertTrue(prove_live_writer(probe))
            self.assertTrue(lock.exists(), 'live writer must remain fenced by retained lock')
            self.assertFalse(P.ACTIVE_LOCKS.get())

    def test_writer_registration_precedes_spawn_and_later_success_cannot_clear_it(self):
        lock = self.root / 'prepare.lock'
        with contextlib.redirect_stderr(io.StringIO()):
            with P.lock(lock) as lease:
                def ambiguous_spawn(*args):
                    self.assertEqual(len(lease.writers), 1)
                    self.assertTrue(lease.unsafe)
                    self.assertIsNone(lease.writers[0].tree)
                    raise OSError('ambiguous spawn failure')
                with mock.patch.object(P, 'ProcessTree', side_effect=ambiguous_spawn), self.assertRaises(OSError):
                    P.run(['fixture'], self.root, dict(os.environ), self.root / 'first.log')
                P.run([sys.executable, '-c', 'pass'], self.root, dict(os.environ), self.root / 'second.log', timeout=5)
                self.assertEqual(len(lease.writers), 2)
                self.assertFalse(lease.writers[0].drained)
                self.assertTrue(lease.writers[1].drained)
                self.assertTrue(lease.unsafe)
        self.assertTrue(lock.exists())
        self.assertFalse(P.ACTIVE_LOCKS.get())
        separate = self.root / 'unrelated.lock'
        with P.lock(separate) as unrelated:
            self.assertFalse(unrelated.unsafe)
        self.assertFalse(separate.exists())

    def test_nested_locks_share_same_writer_token_and_restore_context(self):
        outer_path, inner_path = self.root / 'outer.lock', self.root / 'inner.lock'
        with P.lock(outer_path) as outer:
            with P.lock(inner_path) as inner:
                P.run([sys.executable, '-c', 'pass'], self.root, dict(os.environ), self.root / 'log', timeout=5)
                self.assertIs(outer.writers[0], inner.writers[0])
                self.assertTrue(inner.writers[0].drained)
                self.assertFalse(outer.unsafe)
                self.assertFalse(inner.unsafe)
            self.assertEqual(P.ACTIVE_LOCKS.get(), (outer,))
        self.assertFalse(P.ACTIVE_LOCKS.get())
        self.assertFalse(outer_path.exists())
        self.assertFalse(inner_path.exists())

    def test_real_sigint_at_spawn_signal_restoration_drains_descendant(self):
        # Deliver at generator return AFTER it restores SIGINT, before the
        # caller reaches wait_tree. This reproduces the checkpoint-2 gap.
        restore_code = P.ignore_interrupts.__wrapped__.__code__
        previous_trace = sys.gettrace()
        delivered = []
        def trace(frame, event, arg):
            if (not delivered and frame.f_code is restore_code and event == 'return'
                    and signal.getsignal(signal.SIGINT) != signal.SIG_IGN):
                deadline = time.monotonic() + 5
                while not self.ready.exists() and time.monotonic() < deadline:
                    time.sleep(.01)
                self.assertTrue(self.ready.exists(), 'descendant was not started')
                delivered.append(True)
                signal.raise_signal(signal.SIGINT)
            return trace
        lock = self.root / 'engine-link.lock'
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt):
                with P.lock(lock):
                    P.run(self.argv, self.root, dict(os.environ), self.root / 'log', timeout=5)
        finally:
            sys.settrace(previous_trace)
        self.assertEqual(delivered, [True])
        self.assertFalse(lock.exists())
        self.assert_no_late_write()


class FakeMember:
    def __init__(self, pid, path):
        self.pid, self.path = pid, str(path)
        self.running, self.member = True, True
        self.terminations, self.waits, self.closes = 0, 0, 0
        self.on_terminate = None

    def alive(self):
        return self.running

    def in_job(self):
        return self.member

    def image(self):
        return self.path

    def terminate(self):
        self.terminations += 1
        if self.on_terminate:
            self.on_terminate()
        self.running = False

    def wait(self, timeout):
        self.waits += 1
        if self.running:
            raise TimeoutError('fixture helper still running')

    def close(self):
        self.closes += 1


class FakeJob:
    def __init__(self, members):
        self.members = {member.pid:member for member in members}
        self.name = 'fixture-owned-job'

    def pids(self):
        return [pid for pid, member in self.members.items() if member.running]

    def open_member(self, pid):
        return self.members[pid]

    def active(self):
        return bool(self.pids())


class VctipPolicyTests(unittest.TestCase):
    """Business policy fixtures; Win32 APIs are NOT executed by these fakes."""
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='optimizer-helper-policy-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.image = self.root / 'vctip.exe'
        self.image.write_bytes(b'original fixture helper')
        self.policy = dict(path=str(self.image), sha256=P.sha(self.image))
        self.member = FakeMember(11, self.image)
        self.job = FakeJob([self.member])
        self.audit = []

    def retire(self):
        return P.retire_vctip(self.job, self.policy, self.audit, timeout=.2)

    def test_approved_handle_terminated_waited_and_closed_then_job_zero(self):
        self.assertTrue(self.retire())
        self.assertEqual((self.member.terminations, self.member.waits, self.member.closes), (1, 1, 1))
        self.assertFalse(self.job.active())
        self.assertEqual(self.audit[0]['sha256'], self.policy['sha256'])
        self.assertEqual(self.audit[0]['action'], 'terminate-pinned-helper')
        self.assertTrue(self.audit[0]['exited'])

    def test_no_policy_does_not_open_or_terminate_any_member(self):
        with mock.patch.object(self.job, 'pids') as snapshot:
            self.assertFalse(P.retire_vctip(self.job, None, []))
        snapshot.assert_not_called()
        self.assertEqual(self.member.terminations, 0)

    def test_same_basename_wrong_path_and_hash_mismatch_rejected(self):
        alternate = self.root / 'other/vctip.exe'
        alternate.parent.mkdir()
        alternate.write_bytes(self.image.read_bytes())
        self.member.path = str(alternate)
        self.assertFalse(self.retire())
        self.assertEqual(self.member.terminations, 0)
        self.member.path = str(self.image)
        self.image.write_bytes(b'changed image')
        self.assertFalse(self.retire())
        self.assertEqual(self.member.terminations, 0)
        self.assertEqual(self.member.closes, 2)

    def test_same_pid_outside_job_or_vanished_is_not_approved(self):
        self.member.member = False
        self.assertFalse(self.retire())
        self.assertEqual(self.member.terminations, 0)
        self.assertEqual(self.member.closes, 1)
        with mock.patch.object(self.job, 'open_member', side_effect=OSError('PID vanished')):
            self.assertFalse(self.retire())
        self.assertEqual(self.member.terminations, 0)

    def test_mixed_snapshot_never_retires_even_first_approved_member(self):
        unknown = FakeMember(12, self.root / 'clang.exe')
        self.job.members[12] = unknown
        self.assertFalse(self.retire())
        self.assertEqual(self.member.terminations, 0)
        self.assertEqual(unknown.terminations, 0)
        self.assertEqual((self.member.closes, unknown.closes), (1, 1))

    def test_incomplete_or_unreadable_snapshot_never_retires(self):
        with mock.patch.object(self.job, 'pids', side_effect=RuntimeError('incomplete PID list')):
            self.assertFalse(self.retire())
        self.assertEqual(self.member.terminations, 0)

    def test_membership_or_image_changes_before_action_are_rejected(self):
        with mock.patch.object(self.member, 'in_job', side_effect=[True, False]):
            self.assertFalse(self.retire())
        self.assertEqual(self.member.terminations, 0)
        with mock.patch.object(self.member, 'image', side_effect=[str(self.image), str(self.root / 'other.exe')]):
            self.assertFalse(self.retire())
        self.assertEqual(self.member.terminations, 0)
        self.assertEqual(self.member.closes, 2)

    def test_image_hash_change_during_recheck_is_rejected(self):
        with mock.patch.object(P, 'sha', side_effect=[self.policy['sha256'], 'changed']):
            self.assertFalse(self.retire())
        self.assertEqual(self.member.terminations, 0)

    def test_new_unknown_child_after_snapshot_prevents_monitor_success(self):
        unknown = FakeMember(12, self.root / 'late-compiler.exe')
        self.member.on_terminate = lambda: self.job.members.update({12:unknown})
        tree = mock.Mock()
        tree.process.poll.return_value = 0
        tree.active.side_effect = self.job.active
        tree.job, tree.survivor_policy = self.job, self.policy
        tree.audit = dict(helpers=[])
        with self.assertRaises(subprocess.TimeoutExpired):
            P.monitor_command(tree, ['fixture'], .15)
        self.assertEqual(self.member.terminations, 1)
        self.assertTrue(unknown.running)
        self.assertEqual(unknown.terminations, 0)

    def test_failed_primary_does_not_enter_success_helper_policy(self):
        tree = mock.Mock()
        tree.process.poll.return_value = 9
        tree.audit = dict(helpers=[])
        with mock.patch.object(P, 'retire_vctip') as retire, self.assertRaises(subprocess.CalledProcessError) as caught:
            P.monitor_command(tree, ['fixture'], 10)
        self.assertEqual(caught.exception.returncode, 9)
        self.assertEqual(tree.audit['primaryExit'], 9)
        retire.assert_not_called()

    def test_termination_or_wait_failure_closes_handles_and_propagates(self):
        with mock.patch.object(self.member, 'terminate', side_effect=OSError('terminate denied')):
            with self.assertRaisesRegex(OSError, 'terminate denied'):
                self.retire()
        self.assertEqual(self.member.closes, 1)
        with mock.patch.object(self.member, 'wait', side_effect=TimeoutError('wait failed')):
            with self.assertRaisesRegex(TimeoutError, 'wait failed'):
                self.retire()
        self.assertEqual(self.member.closes, 2)

    def test_retirement_failure_and_failed_job_cleanup_keep_unsafe_lease(self):
        tree = mock.Mock()
        tree.job, tree.survivor_policy = self.job, self.policy
        tree.process.poll.return_value = 0
        tree.process.pid = 123
        tree.active.return_value = True
        tree.terminate.side_effect = OSError('owned-job cleanup failed')
        log, lock = self.root / 'log', self.root / 'operation.lock'
        with mock.patch.object(P, 'ProcessTree', return_value=tree), mock.patch.object(self.member, 'terminate', side_effect=OSError('helper termination denied')):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(P.UndrainedProcessError) as caught:
                with P.lock(lock) as lease:
                    P.run(['fixture'], self.root, dict(os.environ), log, survivor=self.policy)
        self.assertIn('helper termination denied', str(caught.exception.__cause__))
        self.assertTrue(lease.unsafe)
        self.assertTrue(lock.exists())
        audit = json.loads((self.root / 'log.process.json').read_text())
        self.assertEqual(audit['primaryExit'], 0)
        self.assertFalse(audit['drained'])

    def test_audit_failure_does_not_mask_primary_or_release_unknown_lease(self):
        tree = mock.Mock()
        tree.process.poll.return_value = 7
        tree.process.pid = 123
        tree.terminate.side_effect = OSError('cleanup denied')
        primary = subprocess.CalledProcessError(7, ['fixture'])
        lock = self.root / 'operation.lock'
        with mock.patch.object(P, 'ProcessTree', return_value=tree), mock.patch.object(P, 'monitor_command', side_effect=primary), mock.patch.object(P, 'atomic_json', side_effect=OSError('audit write denied')):
            with contextlib.redirect_stderr(io.StringIO()) as errors, self.assertRaises(P.UndrainedProcessError) as caught:
                with P.lock(lock) as lease:
                    P.run(['fixture'], self.root, dict(os.environ), self.root / 'log')
        self.assertIs(caught.exception.__cause__, primary)
        self.assertTrue(lease.unsafe)
        self.assertTrue(lock.exists())
        self.assertIn('audit write denied', errors.getvalue())


class WindowsPidLayoutTests(unittest.TestCase):
    """Exercise actual parser with synthetic bytes, without calling Win32."""
    def job(self, query):
        job = P.WindowsJob.__new__(P.WindowsJob)
        job.C = types.SimpleNamespace(create_string_buffer=ctypes.create_string_buffer,
                                      sizeof=ctypes.sizeof, c_size_t=ctypes.c_size_t,
                                      get_last_error=lambda:234, WinError=lambda n:OSError(n, 'fixture error'))
        job.W = types.SimpleNamespace(DWORD=ctypes.c_uint32)
        job.k = types.SimpleNamespace(QueryInformationJobObject=query)
        job.handle = 99
        return job

    def test_ulong_ptr_entries_and_bounded_growth(self):
        capacities = []
        def query(handle, info, buffer, size, returned):
            self.assertEqual((handle, info), (99, 3))
            capacity = (size - 8) // ctypes.sizeof(ctypes.c_size_t)
            capacities.append(capacity)
            if capacity < 17:
                return 0  # ERROR_MORE_DATA
            (ctypes.c_uint32 * 2).from_buffer(buffer)[:] = [17, 17]
            values = (ctypes.c_size_t * 17).from_buffer(buffer, 8)
            values[:] = list(range(1, 18))
            return 1
        self.assertEqual(self.job(query).pids(), list(range(1, 18)))
        self.assertEqual(capacities, [16, 32])

    def test_success_with_truncated_snapshot_is_rejected(self):
        def query(handle, info, buffer, size, returned):
            (ctypes.c_uint32 * 2).from_buffer(buffer)[:] = [17, 16]
            return 1
        with self.assertRaisesRegex(RuntimeError, 'Incomplete'):
            self.job(query).pids()

    def test_growth_exhaustion_is_bounded(self):
        calls = []
        def query(*args):
            calls.append(1)
            return 0
        with self.assertRaisesRegex(RuntimeError, 'bounded capacity'):
            self.job(query).pids()
        self.assertEqual(len(calls), 9)  # 16 through4096, no unbounded retry.

    def test_empty_snapshot_has_no_spurious_pid(self):
        def query(handle, info, buffer, size, returned):
            (ctypes.c_uint32 * 2).from_buffer(buffer)[:] = [0, 0]
            return 1
        self.assertEqual(self.job(query).pids(), [])


class UndrainedChainTests(unittest.TestCase):
    def test_both_cause_and_suppressed_context_are_checked(self):
        outer = KeyboardInterrupt()
        outer.__cause__ = ValueError('ordinary cause')
        outer.__context__ = P.UndrainedProcessError('unconfirmed writers')
        outer.__suppress_context__ = True
        self.assertTrue(P.has_undrained_error(outer))
        outer.__context__ = None
        outer.__cause__.__cause__ = P.UndrainedProcessError('nested cause')
        self.assertTrue(P.has_undrained_error(outer))

    def test_cycle_terminates_without_losing_other_branch(self):
        first, second = ValueError(), RuntimeError()
        first.__context__, second.__context__ = second, first
        self.assertFalse(P.has_undrained_error(first))
        second.__cause__ = P.UndrainedProcessError('other branch')
        self.assertTrue(P.has_undrained_error(first))
        self.assertFalse(P.has_undrained_error(None))

    def test_budget_exhaustion_retains_ownership_conservatively(self):
        outer = current = ValueError()
        for unused in range(70):
            current.__context__ = ValueError()
            current = current.__context__
        self.assertTrue(P.has_undrained_error(outer))


class SemanticOracleTests(unittest.TestCase):
    def test_original_fixture_oracle_rejects_rhs_loss(self):
        node = shutil.which('node')
        if not node:
            self.skipTest('Node unavailable for original semantic oracle')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, verifier = root / 'input.js', root / 'verify.cjs'
            source.write_text(P.PROBE)
            verifier.write_text(P.VERIFY)
            subprocess.run([node, verifier, source], check=True, capture_output=True)
            source.write_text(P.PROBE.replace('(x=1,x|0)|m', '(x=1,x|0)'))
            result = subprocess.run([node, verifier, source], capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
