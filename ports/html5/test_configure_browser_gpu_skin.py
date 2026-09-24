"""Opt-in orchestration tests; no PowerShell, UBT or Windows execution."""
import importlib.util
import json
import ntpath
import os
import re
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('gpu_config', HERE / 'configure-browser-gpu-skin.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)
ORIGINAL_LOAD = C.load_patcher
admission_spec = importlib.util.spec_from_file_location('admission', HERE / 'browser-build-admission.py')
A = importlib.util.module_from_spec(admission_spec)
admission_spec.loader.exec_module(A)


class ExperimentGate(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.module = ORIGINAL_LOAD()
        self.specs = []
        runtime = '{ const int32 MaxGPUSkinBones=GetFeatureLevelMaxNumberOfBones(FeatureLevel); const int32 MaxBonesPerChunk=GetMaxBonesPerSection(); OLD }'
        cache = '{ OLD { return false; } return Material->IsUsedWithSkeletalMesh() || Material->IsSpecialEngineMaterial(); }'
        (self.root / '.tournament-browser-port').touch()
        version = self.root / 'Engine/Build/Build.version'
        version.parent.mkdir(parents=True)
        version.write_text(json.dumps(dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
        for item, body in zip(self.module.SPECS, [runtime, cache]):
            body = body.replace('OLD', item['old'])
            pinned = dict(item, body_sha256=self.module.digest(body.encode()))
            if item['name'] == 'runtime':
                pinned['previous_body_sha256'] = self.module.digest(body.replace(item['old'], self.module.RUNTIME_PREVIOUS).encode())
            self.specs.append(pinned)
            source = (self.module.INCLUDE_ANCHOR + '\n' if item['name'] == 'runtime' else '') + item['signature'] + '\n' + body + '\n'
            path = self.root / item['path']
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(source)
        self.module.SPECS = tuple(self.specs)
        scoped = patch.object(C, 'load_patcher', return_value=self.module)
        scoped.start()
        self.addCleanup(scoped.stop)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def test_default_off_even_apply_is_read_only(self):
        before = self.snapshot()
        result = C.configure(self.root, apply=True)
        self.assertFalse(result['enabled'])
        self.assertFalse(result['sourceApplied'])
        self.assertFalse(result['validated'])
        self.assertEqual(before, self.snapshot())

    def test_enabled_preflight_only_does_not_apply(self):
        before = self.snapshot()
        result = C.configure(self.root, True)
        self.assertTrue(result['enabled'])
        self.assertFalse(result['sourceApplied'])
        self.assertTrue(result['requiresFreshShaderCook'])
        self.assertEqual(before, self.snapshot())

    def test_same_flag_both_phases_identical_source_inputs(self):
        editor = C.configure(self.root, True, True, 'native-editor')
        runtime = C.configure(self.root, True, True, 'html5')
        self.assertEqual(editor['sources'], runtime['sources'])
        self.assertEqual(editor['patcherSha256'], runtime['patcherSha256'])
        for result in [editor, runtime]:
            self.assertTrue(result['sourceApplied'])
            self.assertTrue(result['requiresMatchingRuntimeAndPackage'])
            self.assertFalse(result['validated'])
            self.assertEqual(result['status'], 'source-inputs-only')

    def test_missing_flag_after_apply_refuses_without_rollback(self):
        C.configure(self.root, True, True)
        before = self.snapshot()
        for phase in ['native-editor', 'html5']:
            with self.assertRaisesRegex(ValueError, 'already present'):
                C.configure(self.root, False, True, phase)
            self.assertEqual(before, self.snapshot())

    def test_missing_flag_refuses_partial_pair(self):
        C.configure(self.root, True, True)
        path = self.root / self.specs[1]['path']
        path.write_bytes(Path(str(path) + self.module.BACKUP_SUFFIX).read_bytes())
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'already present'):
            C.configure(self.root)
        self.assertEqual(before, self.snapshot())
        self.assertTrue(C.configure(self.root, True, True)['sourceApplied'])

    def test_missing_backup_refuses_enable(self):
        C.configure(self.root, True, True)
        Path(str(self.root / self.specs[0]['path']) + self.module.BACKUP_SUFFIX).unlink()
        with self.assertRaises(ValueError):
            C.configure(self.root, True, True)

    def previous_runtime_only(self):
        item = self.specs[0]
        path = self.root / item['path']
        original = path.read_bytes()
        Path(str(path) + self.module.BACKUP_SUFFIX).write_bytes(original)
        corrected = self.module.transform(original, item)
        path.write_bytes(corrected.replace(self.module.RUNTIME_NEW.encode(), self.module.RUNTIME_PREVIOUS.encode(), 1))
        return path, original, corrected

    def test_previous_runtime_only_requires_flag_and_exact_backup(self):
        path, original, corrected = self.previous_runtime_only()
        before = self.snapshot()
        for phase in ['native-editor', 'html5']:
            with self.assertRaisesRegex(ValueError, 'already present'):
                C.configure(self.root, False, True, phase)
            self.assertEqual(before, self.snapshot())
        result = C.configure(self.root, True)
        self.assertFalse(result['sourceApplied'])
        self.assertEqual(before, self.snapshot())
        result = C.configure(self.root, True, True)
        self.assertTrue(result['sourceApplied'])
        self.assertEqual(path.read_bytes(), corrected)
        self.assertEqual(Path(str(path) + self.module.BACKUP_SUFFIX).read_bytes(), original)

    def test_previous_runtime_missing_backup_cannot_be_adopted(self):
        path, original, corrected = self.previous_runtime_only()
        Path(str(path) + self.module.BACKUP_SUFFIX).unlink()
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'requires original backup'):
            C.configure(self.root, True, True)
        self.assertEqual(before, self.snapshot())

    def test_unknown_phase_and_missing_marker_refused(self):
        with self.assertRaises(ValueError):
            C.configure(self.root, phase='automatic-promotion')
        (self.root / '.tournament-browser-port').unlink()
        with self.assertRaises(ValueError):
            C.configure(self.root, True, True)

    def test_editor_plan_includes_engine_editor_and_worker_without_cook(self):
        commands = C.editor_commands(self.root)
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][1:4], ['UnrealTournamentEditor', 'Win64', 'Development'])
        self.assertNotIn('-Module', commands[0])
        self.assertEqual(commands[1][1:6], ['ShaderCompileWorker', 'Win64', 'Development', '-Module', 'ShaderFormatOpenGL'])
        for command in commands:
            self.assertIn('-NoHotReload', command)
            self.assertIn('-2015', command)
            self.assertNotIn('-run=Cook', command)

    def test_wrapper_flag_default_off_and_explicit_forwarding_order(self):
        for filename, phase in [('build-legacy.ps1', 'html5'), ('build-browser-editor.ps1', 'native-editor')]:
            text = (HERE / filename).read_text()
            self.assertIn('[switch]$ExperimentalGpuSkin8', text)
            self.assertNotIn('$ExperimentalGpuSkin8=', text)
            self.assertIn("if($ExperimentalGpuSkin8){$gpuArgs+='--experimental-gpu-skin8'}", text)
            self.assertIn("'--phase','" + phase + "'", text)
            preflight = text.index('configure-browser-gpu-skin.py" @gpuArgs')
            apply = text.index('configure-browser-gpu-skin.py" @gpuArgs --apply')
            self.assertLess(preflight, apply)
            boundary = text.index("if($LASTEXITCODE){throw 'Editor/compiler admission failed")
            self.assertLess(boundary, apply)
            self.assertNotIn('Copy-Item', text)
            self.assertNotIn('Start-Process', text)

    def test_shared_admission_immediately_precedes_both_apply_calls(self):
        for filename in ['build-legacy.ps1', 'build-browser-editor.ps1']:
            text = (HERE / filename).read_text()
            self.assertEqual(text.count('browser-build-admission.py'), 1)
            guard = text.index('browser-build-admission.py')
            apply = text.index('configure-browser-gpu-skin.py" @gpuArgs --apply')
            between = text[guard:apply]
            self.assertIn('if($LASTEXITCODE){throw', between)
            self.assertNotIn('prepare-browser-optimizer.py', between)
            self.assertNotIn('Set-Content', between)

    def test_native_wrapper_failure_and_environment_restore_structure(self):
        text = (HERE / 'build-browser-editor.ps1').read_text()
        self.assertIn('if($code -ne 0){throw', text)
        self.assertIn('finally {Pop-Location}', text)
        self.assertIn("finally {[Environment]::SetEnvironmentVariable('TOURNAMENT_UT4_UCRT_VERSION',$priorUcrt,'Process')}", text)

    def test_frozen_patcher_hash_enforced(self):
        with patch.object(Path, 'read_bytes', return_value=b'altered'):
            with self.assertRaisesRegex(ValueError, 'reviewed source'):
                ORIGINAL_LOAD()


class EditorAdmission(unittest.TestCase):
    root = 'F:/TournamentUT4/browser-port'
    foreign = 'F:/TournamentUT4/source/UnrealTournament-clean-master'

    def process(self, engine=None, project=None, editor='UE4Editor.exe'):
        engine = engine or self.foreign
        exe = engine + '/Engine/Binaries/Win64/' + editor
        project = project or engine + '/UnrealTournament/UnrealTournament.uproject'
        args = [exe, project, '-server', '-port=5090']
        return dict(Name=editor, ProcessId=42, ExecutablePath=exe, CommandLine=args)

    def evaluate(self, process, bad_paths=()):
        exe = process.get('ExecutablePath')
        # Test-only physical path oracle. Production uses lstat of each ancestor
        # and the reviewed no-hardlink/no-reparse checker on Windows.
        known = set()
        if isinstance(exe, str):
            try:
                normalized = A.normalize(exe)
                known.add(normalized)
                suffix = '\\engine\\binaries\\win64\\' + ntpath.basename(normalized)
                if normalized.endswith(suffix):
                    root = normalized[:-len(suffix)]
                    known.update([root, root + '\\engine\\build\\build.version'])
            except ValueError:
                pass
        for arg in process.get('CommandLine') or []:
            try:
                path = arg.split('=', 1)[1] if arg.lower().startswith('-project=') else arg
                if path.lower().endswith('.uproject'):
                    known.add(A.normalize(path))
            except ValueError:
                pass
        bad = {A.normalize(path) for path in bad_paths}

        def physical(path, directory):
            normalized = A.normalize(path)
            if normalized not in known or normalized in bad:
                raise OSError('unverified physical path')

        return A.editor_reason(self.root, process, physical, decode=lambda args: args)

    def test_selected_executable_blocks_and_known_foreign_server_continues(self):
        self.assertIn('selected root', self.evaluate(self.process(engine=self.root)))
        self.assertIsNone(self.evaluate(self.process()))
        self.assertIsNone(self.evaluate(self.process(editor='UE4Editor-Cmd.exe')))

    def test_foreign_executable_selected_project_blocks_case_insensitively(self):
        selected = (self.root + '/UnrealTournament/UnrealTournament.uproject').upper()
        process = self.process(project=selected)
        self.assertIn('selected root', self.evaluate(process))
        process['CommandLine'][1] = '-Project=' + selected
        self.assertIn('selected root', self.evaluate(process))
        process['CommandLine'][1:2] = ['-project', selected]
        self.assertIn('selected root', self.evaluate(process))

    def test_prefix_lookalike_is_foreign_only_when_physically_verified(self):
        for foreign in [self.root + '-other', self.root + '2']:
            process = self.process(engine=foreign)
            self.assertIsNone(self.evaluate(process))
            self.assertIn('unknown', self.evaluate(process, [process['ExecutablePath']]))
        self.assertTrue(A.within(A.normalize(self.root + '/Engine/file'), A.normalize(self.root)))
        self.assertFalse(A.within(A.normalize(self.root + '-other/Engine/file'), A.normalize(self.root)))

    def test_unknown_relative_missing_and_third_root_paths_fail_closed(self):
        for field, value in [('ExecutablePath', None), ('ExecutablePath', 'UE4Editor.exe'), ('CommandLine', None)]:
            process = self.process()
            process[field] = value
            self.assertIn('unknown', self.evaluate(process))
        for project in ['UnrealTournament.uproject', 'F:relative.uproject', 'C:/unverified/project.uproject']:
            self.assertIn('unknown', self.evaluate(self.process(project=project)))
        process = self.process()
        process['CommandLine'] = [process['ExecutablePath'], '-server']
        self.assertIn('unknown', self.evaluate(process))

    def test_changed_executable_multiple_projects_and_inaccessible_paths_block(self):
        process = self.process()
        process['CommandLine'][0] = self.root + '/Engine/Binaries/Win64/UE4Editor.exe'
        self.assertIn('unknown', self.evaluate(process))
        process = self.process()
        process['CommandLine'].append(self.foreign + '/Other/Other.uproject')
        self.assertIn('unknown', self.evaluate(process))
        process = self.process()
        self.assertIn('unknown', self.evaluate(process, [process['CommandLine'][1]]))
        self.assertIn('unknown', self.evaluate(process, [self.foreign + '/Engine/Build/Build.version']))

    def test_compilers_block_globally_without_editor_path_evidence(self):
        names = ['cl.exe', 'link.exe', 'MSBuild.exe', 'clang++.exe', 'UnrealBuildTool.exe', 'ShaderCompileWorker.exe']
        records = [dict(Name=name, ProcessId=i, ExecutablePath=None, CommandLine=None) for i, name in enumerate(names)]
        records += [dict(Name='python.exe', ProcessId=99, CommandLine='python emcc.py input.cpp')]
        def never(*args):
            self.fail('Compiler check must not need editor path proof')
        self.assertEqual(len(A.blockers(self.root, records, never)), len(records))
        self.assertEqual(A.blockers(self.root, [dict(Name='Code.exe', CommandLine='')], never), [])

    def test_quoted_emcc_python_script_blocks_globally_between_children(self):
        command = '"C:\\Python\\python.exe" "F:\\Browser\\Engine\\Extras\\ThirdPartyNotUE\\emsdk\\emcc.py" -c physics.cpp'
        args = ['C:\\Python\\python.exe', 'F:\\Browser\\Engine\\Extras\\ThirdPartyNotUE\\emsdk\\emcc.py', '-c', 'physics.cpp']
        decoded = []
        def decode(text):
            decoded.append(text)
            return args
        def no_physical(*unused):
            self.fail('Global compiler detection must not consult editor ownership')
        for name in ['python.exe', 'Python3.exe', 'python3.11.exe', 'pythonw.exe', 'py.exe']:
            found = A.blockers(self.root, [dict(Name=name, ProcessId=52, CommandLine=command)], no_physical, decode)
            self.assertEqual(found[0]['reason'], 'emcc Python driver active (global guard)')
        self.assertEqual(decoded, [command] * 5)
        for script in ['F:/SDK/EMCC.PY', 'F:/SDK/emcc', 'emcc.py']:
            found = A.blockers(self.root, [dict(Name='python.exe', CommandLine=command)], no_physical, lambda _: ['python', '-I', '-S', script])
            self.assertTrue(found)

    def test_python_unknown_intent_blocks_and_unrelated_parsed_script_allows(self):
        def no_physical(*unused):
            self.fail('Python policy must not consult editor ownership')
        process = dict(Name='python.exe', CommandLine=None)
        for decoded in [[], None, ['python', None]]:
            found = A.blockers(self.root, [process], no_physical, lambda _: decoded)
            self.assertIn('unknown', found[0]['reason'])
        def fails(_):
            raise OSError('CIM command inaccessible')
        self.assertIn('unknown', A.blockers(self.root, [process], no_physical, fails)[0]['reason'])
        for args in [['python', 'F:/tools/report.py'], ['python', 'F:/tools/not-emcc.py'], ['python', '-c', 'print(1)']]:
            self.assertEqual(A.blockers(self.root, [process], no_physical, lambda _: args), [])

    @unittest.skipUnless(os.name == 'nt', 'Win32 argv API executes only on Windows')
    def test_real_windows_argv_quoted_paths(self):
        args = ['F:\\Program Files\\UE\\Engine\\Binaries\\Win64\\UE4Editor.exe', '-project=F:\\Program Files\\UE\\Game\\A.uproject', '-server']
        self.assertEqual(A.windows_argv(subprocess.list2cmdline(args)), args)
        with self.assertRaises(ValueError):
            A.windows_argv('')
        command = '"C:\\Python\\python.exe" "F:\\Browser\\Engine\\Extras\\ThirdPartyNotUE\\emsdk\\emcc.py" -c physics.cpp'
        found = A.blockers(self.root, [dict(Name='python.exe', CommandLine=command)], lambda *args: self.fail('unexpected physical query'))
        self.assertEqual(found[0]['reason'], 'emcc Python driver active (global guard)')


if __name__ == '__main__':
    unittest.main()
