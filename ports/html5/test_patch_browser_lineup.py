"""Original guard tests plus privately extracted actual-callback regressions.

Run: python3 -B test_patch_browser_lineup.py --source /private/UTLineUpHelper.cpp
The optional --source is read only; without it actual-body tests explicitly skip.
All writes, backups, C++ harnesses and binaries are confined to temporary dirs.
No licensed callback is bundled. No engine build, network or process control.
"""
import argparse
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location('lineup_patcher', Path(__file__).with_name('patch-browser-lineup.py'))
P = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(P)
ACTUAL_SOURCE = os.environ.get('UT4_LINEUP_SOURCE')

# Independently constructed parser/transaction fixture, NOT the licensed body.
# Only filesystem tests mock the pin to this synthetic callback's fingerprint.
SYNTHETIC = '''void AUTLineUpHelper::IntroSpawnDelayedCharacter()
{
    // Inert structural noise: } " {
    if (LineUpSlots.IsValidIndex(Intro_TotalSpawnedPlayers)) { observe(); }
    if (LineUpSlots.IsValidIndex(Intro_TotalSpawnedPlayers))
    {
        observe(LineUpSlots.IsValidIndex(Intro_TotalSpawnedPlayers - 1));
    }
}
'''
SOURCE = '// original synthetic fixture\n' + SYNTHETIC + '\nvoid untouched() { check(true); }\n'


class TransactionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='ut4-lineup-guards-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.pin = mock.patch.object(P, 'SOURCE_SHA256', P.digest_method(SYNTHETIC.rstrip()))
        self.pin.start()
        self.addCleanup(self.pin.stop)
        (self.root / '.tournament-browser-port').touch()
        self.version = self.root / 'Engine/Build/Build.version'
        self.version.parent.mkdir(parents=True)
        self.revision = dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)
        self.version.write_text(json.dumps(self.revision))
        self.source = self.root / P.SOURCE_PATH
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'\xef\xbb\xbf' + SOURCE.replace('\n', '\r\n').encode())
        self.backup = Path(str(self.source) + P.BACKUP_SUFFIX)

    def patch(self, apply=True, root=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return P.patch(root or self.root, apply)

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob('*') if p.is_file()}

    def reject(self, root=None):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.patch(root=root)
        self.assertEqual(before, self.snapshot())

    def test_preflight_no_writes(self):
        before = self.snapshot()
        self.assertEqual(self.patch(False)['status'], 'would-patch')
        self.assertEqual(before, self.snapshot())

    def test_apply_backup_bom_crlf_and_exact_boundary(self):
        before = self.source.read_bytes()
        self.assertEqual(self.patch()['status'], 'patched')
        self.assertEqual(self.backup.read_bytes(), before)
        after = self.source.read_bytes()
        self.assertTrue(after.startswith(b'\xef\xbb\xbf'))
        self.assertNotIn(b'\n', after.replace(b'\r\n', b''))
        original, _ = P.decode(before)
        changed, _ = P.decode(after)
        a, b = P.method_span(original)
        c, d = P.method_span(changed)
        self.assertEqual(original[:a], changed[:c])
        self.assertEqual(original[b:], changed[d:])
        self.assertEqual(changed.count('if (' + P.CURRENT + ')'), 1)
        self.assertEqual(changed.count(P.BOUNDED_CURRENT), 1)
        self.assertEqual(changed.count(P.BOUNDED_PREVIOUS), 1)
        self.assertIn('check(true)', changed)

    def test_idempotent_without_timestamp_changes(self):
        self.patch()
        before = self.snapshot()
        times = [p.stat().st_mtime_ns for p in (self.source, self.backup)]
        self.assertEqual(self.patch()['status'], 'already-patched')
        self.assertEqual(before, self.snapshot())
        self.assertEqual(times, [p.stat().st_mtime_ns for p in (self.source, self.backup)])

    def test_matching_backup_preserved(self):
        self.backup.write_bytes(self.source.read_bytes())
        timestamp = self.backup.stat().st_mtime_ns
        self.patch()
        self.assertEqual(self.backup.stat().st_mtime_ns, timestamp)

    def test_marker_and_each_revision_field_required(self):
        marker = self.root / '.tournament-browser-port'
        marker.unlink()
        self.reject()
        marker.touch()
        for key in self.revision:
            with self.subTest(key=key):
                self.version.write_text(json.dumps({**self.revision, key: self.revision[key] + 1}))
                self.reject()

    def test_exact_callback_fingerprint_and_unique_definition(self):
        for source in [SOURCE.replace('observe();', 'other();'), SOURCE + SYNTHETIC,
                       SOURCE.replace('observe();', 'observe(); check(false);'),
                       SOURCE.replace('void AUTLineUpHelper', '// void AUTLineUpHelper')]:
            with self.subTest(case=source[:30]):
                self.source.write_text(source)
                self.reject()

    def test_partial_misplaced_or_modified_patch(self):
        changed = P.transform(SOURCE)
        variants = [changed.replace(' && Intro_TimeDelaysOnAnims.IsValidIndex(Intro_TotalSpawnedPlayers)', ''),
                    changed.replace(P.BOUNDED_PREVIOUS, P.PREVIOUS),
                    changed.replace('observe();', 'changed();'),
                    SOURCE + '// ' + P.MARKER,
                    changed + '// ' + P.MARKER,
                    changed.replace('// ' + P.MARKER + '\n', '').replace('void untouched()', '// ' + P.MARKER + '\nvoid untouched()')]
        for source in variants:
            with self.subTest(case=len(source)):
                with self.assertRaises(ValueError):
                    P.transform(source)

    def test_conflicting_backup_and_missing_original(self):
        self.backup.write_text('unrelated backup')
        self.reject()
        self.backup.unlink()
        self.patch()
        self.backup.unlink()
        self.reject()

    def test_altered_backup_rejected_on_reapply(self):
        self.patch()
        self.backup.write_bytes(self.backup.read_bytes() + b'// changed')
        self.reject()

    def test_hardlinked_source_and_backup_do_not_mutate_alias(self):
        alias = self.root / 'shared-original'
        before = self.source.read_bytes()
        os.link(self.source, alias)
        self.reject()
        self.assertEqual(alias.read_bytes(), before)
        alias.unlink()
        self.backup.write_bytes(before)
        os.link(self.backup, alias)
        self.reject()
        self.assertEqual(alias.read_bytes(), before)

    def test_symlink_source_ancestor_and_root(self):
        target = self.source.with_name('real-source')
        self.source.rename(target)
        self.source.symlink_to(target)
        self.reject()
        self.source.unlink()
        target.rename(self.source)
        parent = self.source.parent
        moved = parent.with_name('real-private')
        parent.rename(moved)
        parent.symlink_to(moved, target_is_directory=True)
        self.reject()
        parent.unlink()
        moved.rename(parent)
        alias = self.root / 'root-alias'
        alias.symlink_to(self.root, target_is_directory=True)
        self.reject(root=alias)

    def test_symlink_backup_and_marker_rejected(self):
        alias = self.root / 'backup-real'
        alias.write_bytes(self.source.read_bytes())
        self.backup.symlink_to(alias)
        self.reject()
        self.backup.unlink()
        marker = self.root / '.tournament-browser-port'
        marker.unlink()
        marker.symlink_to(alias)
        self.reject()

    def test_mixed_line_endings(self):
        self.source.write_bytes(self.source.read_bytes() + b'\n')
        self.reject()

    def test_mid_apply_source_change_is_not_overwritten(self):
        original_physical = P.physical
        changed = self.source.read_bytes() + b'// concurrent edit'
        count = 0

        def concurrent(path, *args, **kwargs):
            nonlocal count
            if Path(path) == self.source:
                count += 1
                if count == 2:
                    self.source.write_bytes(changed)
            return original_physical(path, *args, **kwargs)

        with mock.patch.object(P, 'physical', side_effect=concurrent):
            with self.assertRaises(ValueError):
                self.patch()
        self.assertEqual(self.source.read_bytes(), changed)
        self.assertFalse(list(self.source.parent.glob('.lineup-patch-*')))


# Independently implemented C++ array/delegate/world stubs. The actual callback
# is extracted from the caller-supplied private source only inside a tempdir.
HARNESS = r'''
#include <cassert>
#include <functional>
#include <vector>
struct BoundsFault {};
template<class T> struct Array {
    std::vector<T> values;
    int Num() const { return int(values.size()); }
    bool IsValidIndex(int n) const { return n >= 0 && n < Num(); }
    T& operator[](int n) { if (!IsValidIndex(n)) throw BoundsFault{}; return values[n]; }
};
struct AUTCharacter { bool played = false; int GetTeamNum() const { return 0; } };
struct FLineUpSlot { AUTCharacter* CharacterInSpot = nullptr; };
struct AUTPlayerController { int GetTeamNum() const { return 0; } };
struct UUTLocalPlayer { AUTPlayerController* PlayerController = nullptr; };
template<class T, class U> T* Cast(U* p) { return static_cast<T*>(p); }
struct FTimerDelegate {
    std::function<void()> invoke;
    template<class T> static FTimerDelegate CreateUObject(T* object, void(T::*method)()) {
        return {[object, method]() { (object->*method)(); }};
    }
};
struct Timers {
    bool pending = false;
    FTimerDelegate callback;
    std::vector<float> delays;
    void SetTimer(int&, FTimerDelegate next, float delay, bool loop) {
        assert(!loop); delays.push_back(delay); callback = next; pending = delay > 0;
    }
    void Fire() { assert(pending); auto saved = callback; pending = false; saved.invoke(); }
};
struct World {
    UUTLocalPlayer* local = nullptr;
    Timers timers;
    UUTLocalPlayer* GetFirstLocalPlayerFromController() { return local; }
    Timers& GetTimerManager() { return timers; }
};
struct AUTLineUpHelper {
    Array<FLineUpSlot> LineUpSlots;
    Array<FLineUpSlot*> Intro_MyTeamLineUpSlots;
    Array<float> Intro_TimeDelaysOnAnims;
    int Intro_TotalSpawnedPlayers = 0, Intro_NextClientSpawnHandle = 0;
    int animations = 0;
    World world;
    World* GetWorld() { return &world; }
    FLineUpSlot* Intro_GetRandomUnSpawnedLineUpSlot() {
        for (auto& slot : LineUpSlots.values)
            if (slot.CharacterInSpot && !slot.CharacterInSpot->played) return &slot;
        return nullptr;
    }
    void PlayIntroClientAnimationOnCharacter(AUTCharacter* pawn, bool) {
        pawn->played = true; ++animations;
    }
    void IntroSpawnDelayedCharacter();
};
'''
MAIN = r'''
int main() {
    // Unequal arrays, empty schedules, exhausted/negative indices, absent local
    // player: execute the real second block without advancing the counter first.
    for (int slots = 0; slots <= 8; ++slots)
    for (int count = 0; count <= 8; ++count)
    for (int index = -1; index <= 10; ++index) {
        AUTLineUpHelper helper;
        helper.LineUpSlots.values.resize(slots);
        for (int i = 0; i < count; ++i) helper.Intro_TimeDelaysOnAnims.values.push_back(1.f + 2.f*i);
        helper.Intro_TotalSpawnedPlayers = index;
        bool failed = false;
        try { helper.IntroSpawnDelayedCharacter(); } catch (const BoundsFault&) { failed = true; }
        const bool slotValid = index >= 0 && index < slots;
        const bool delayValid = index >= 0 && index < count;
        assert(failed == (!PATCHED && slotValid && !delayValid));
        const bool scheduled = slotValid && delayValid;
        assert(helper.world.timers.pending == scheduled);
        assert(helper.world.timers.delays.size() == (scheduled ? 1u : 0u));
        if (scheduled) assert(helper.world.timers.delays[0] == (index ? 2.f : 1.f));
    }
    AUTPlayerController controller;
    UUTLocalPlayer local; local.PlayerController = &controller;
    // Normal full sequence: initial 1s, then relative 2s and 3s, terminates.
    {
        AUTLineUpHelper helper; AUTCharacter pawns[3]; helper.world.local = &local;
        for (auto& pawn : pawns) { FLineUpSlot slot; slot.CharacterInSpot = &pawn; helper.LineUpSlots.values.push_back(slot); }
        helper.Intro_MyTeamLineUpSlots.values.push_back(&helper.LineUpSlots.values[0]);
        helper.Intro_TimeDelaysOnAnims.values = {1.f, 3.f, 6.f};
        helper.world.timers.SetTimer(helper.Intro_NextClientSpawnHandle,
            FTimerDelegate::CreateUObject(&helper, &AUTLineUpHelper::IntroSpawnDelayedCharacter), 1.f, false);
        for (int i = 0; i < 3; ++i) helper.world.timers.Fire();
        assert(helper.animations == 3 && helper.Intro_TotalSpawnedPlayers == 3);
        assert(!helper.world.timers.pending);
        assert((helper.world.timers.delays == std::vector<float>{1.f, 2.f, 3.f}));
    }
    // Late join between actual timer firings. The newcomer RPC is represented
    // by its existing animation side effect; old schedule has only two entries.
    {
        AUTLineUpHelper helper; AUTCharacter pawns[3]; helper.world.local = &local;
        for (int i = 0; i < 2; ++i) { FLineUpSlot slot; slot.CharacterInSpot = &pawns[i]; helper.LineUpSlots.values.push_back(slot); }
        helper.Intro_TimeDelaysOnAnims.values = {1.f, 3.f};
        helper.world.timers.SetTimer(helper.Intro_NextClientSpawnHandle,
            FTimerDelegate::CreateUObject(&helper, &AUTLineUpHelper::IntroSpawnDelayedCharacter), 1.f, false);
        helper.world.timers.Fire();
        FLineUpSlot newcomer; newcomer.CharacterInSpot = &pawns[2]; helper.LineUpSlots.values.push_back(newcomer);
        helper.PlayIntroClientAnimationOnCharacter(&pawns[2], false);
        bool failed = false;
        try { helper.world.timers.Fire(); } catch (const BoundsFault&) { failed = true; }
        assert(failed == !PATCHED);
        assert(helper.Intro_TotalSpawnedPlayers == 2 && helper.animations == 3);
        assert(!helper.world.timers.pending && helper.world.timers.delays.size() == 2);
        for (auto& pawn : pawns) assert(pawn.played);
    }
    // Slot shrink between timer firings still terminates without touching an
    // otherwise valid, longer delay schedule.
    {
        AUTLineUpHelper helper; helper.Intro_TotalSpawnedPlayers = 1;
        helper.LineUpSlots.values.resize(2); helper.Intro_TimeDelaysOnAnims.values = {1.f, 3.f, 6.f};
        helper.IntroSpawnDelayedCharacter(); assert(helper.world.timers.pending);
        helper.LineUpSlots.values.resize(1);
        helper.world.timers.Fire(); assert(!helper.world.timers.pending);
        assert(helper.world.timers.delays.size() == 1);
    }
}
'''


class ActualBodyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not ACTUAL_SOURCE:
            raise unittest.SkipTest('Supply --source or UT4_LINEUP_SOURCE for actual-body regressions')
        # Private PowerShell captures can append CRLF to an LF source. Normalize
        # only this read-only fixture; production transform still rejects mixed
        # line endings. The complete extracted callback fingerprint is checked.
        cls.source = Path(ACTUAL_SOURCE).read_text(encoding='utf-8-sig')
        left, right = P.method_span(cls.source)
        cls.body = cls.source[left:right]
        if P.digest_method(cls.body) != P.SOURCE_SHA256:
            raise AssertionError('Private fixture is not the pinned unpatched callback')

    def test_actual_pin_and_only_rescheduling_block_changes(self):
        changed = P.transform(self.source)
        a, b = P.method_span(self.source)
        c, d = P.method_span(changed)
        self.assertEqual(self.source[:a], changed[:c])
        self.assertEqual(self.source[b:], changed[d:])
        original_prefix = self.body[:self.body.rindex('if (' + P.CURRENT + ')')].rstrip()
        changed_prefix = changed[c:d].split('// ' + P.MARKER)[0].rstrip()
        self.assertEqual(original_prefix, changed_prefix)
        self.assertEqual(P.transform(changed), changed)

    def test_actual_source_apply_and_backup_only_in_temp_checkout(self):
        with tempfile.TemporaryDirectory(prefix='ut4-lineup-private-apply-') as folder:
            root = Path(folder).resolve()
            (root / '.tournament-browser-port').touch()
            version = root / 'Engine/Build/Build.version'
            version.parent.mkdir(parents=True)
            version.write_text(json.dumps(dict(MajorVersion=4, MinorVersion=15, PatchVersion=0, Changelist=3228288)))
            source = root / P.SOURCE_PATH
            source.parent.mkdir(parents=True)
            original = b'\xef\xbb\xbf' + self.source.replace('\n', '\r\n').encode()
            source.write_bytes(original)  # New bytes, never a hardlink to input.
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(P.patch(root)['status'], 'would-patch')
                self.assertEqual(source.read_bytes(), original)
                self.assertEqual(P.patch(root, True)['status'], 'patched')
                self.assertEqual(P.patch(root, True)['status'], 'already-patched')
            self.assertEqual(Path(str(source) + P.BACKUP_SUFFIX).read_bytes(), original)

    def test_actual_body_baseline_and_patch_compile_and_execute(self):
        compiler = shutil.which('clang++') or shutil.which('c++')
        if not compiler:
            self.fail('Actual-body regression requires a local C++11 compiler')
        with tempfile.TemporaryDirectory(prefix='ut4-lineup-actual-') as folder:
            root = Path(folder).resolve()
            for patched in (0, 1):
                with self.subTest(patched=patched):
                    body = P.transform(self.body) if patched else self.body
                    fixture, binary = root / 'actual.cpp', root / 'actual'
                    fixture.write_text(HARNESS + '\n' + body + '\n' + MAIN)
                    built = subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-Werror',
                                            '-DPATCHED=' + str(patched), str(fixture), '-o', str(binary)],
                                           capture_output=True, text=True, timeout=30)
                    # Avoid printing licensed source lines from compiler output.
                    errors = re.findall(r'(?:fatal )?error: [^\n]*', built.stderr)
                    self.assertEqual(built.returncode, 0, '\n'.join(errors) or 'Private C++ fixture did not compile')
                    result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 0, 'Actual callback regression failed: ' + result.stderr[-1000:])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--source', default=ACTUAL_SOURCE)
    args, remaining = parser.parse_known_args()
    ACTUAL_SOURCE = args.source
    unittest.main(argv=[sys.argv[0], *remaining], verbosity=2)
