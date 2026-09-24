"""Patch only an isolated UE4.15 checkout; never the running host installation.

Epic engine/game source remains in the user's licensed local checkout. This file
contains original configuration code, not a copy of the engine implementation.
"""
import argparse
import json
from pathlib import Path
import shutil


CONFIG_METHOD = r'''
        public static string SetUpEmscriptenConfigFile()
        {
            // Tournament HTML5: explicit paths avoid Python 2 expanduser choosing
            // SSH's home instead of the build-local USERPROFILE used by old UBT.
            Func<string, string> Quote = value => "'" + value.Replace("\\", "/").Replace("'", "\\'") + "'";
            string text = "EMSCRIPTEN_ROOT = " + Quote(EMSCRIPTEN_ROOT) + "\n"
                + "LLVM_ROOT = " + Quote(LLVM_ROOT) + "\n"
                + "NODE_JS = [" + Quote(NODE_JS) + "]\n"
                + "PYTHON = " + Quote(PYTHON) + "\n"
                + "EMSCRIPTEN_NATIVE_OPTIMIZER = " + Quote(Path.Combine(LLVM_ROOT, "optimizer") + PLATFORM_EXE) + "\n"
                + "TEMP_DIR = " + Quote(Path.Combine(HTML5Intermediatory, "EmscriptenTemp")) + "\n"
                + "COMPILER_ENGINE = NODE_JS\nJS_ENGINES = [NODE_JS]\n";
            if (!File.Exists(DOT_EMSCRIPTEN) || File.ReadAllText(DOT_EMSCRIPTEN) != text)
                File.WriteAllText(DOT_EMSCRIPTEN, text);
            Environment.SetEnvironmentVariable("EM_CONFIG", DOT_EMSCRIPTEN);
            Environment.SetEnvironmentVariable("EM_CACHE", EMSCRIPTEN_CACHE);
            Environment.SetEnvironmentVariable("EMSCRIPTEN", EMSCRIPTEN_ROOT);
            Environment.SetEnvironmentVariable("NODEPATH", Path.GetDirectoryName(NODE_JS));
            Environment.SetEnvironmentVariable("NODE", NODE_JS);
            Environment.SetEnvironmentVariable("LLVM", LLVM_ROOT);
            return DOT_EMSCRIPTEN;
        }

'''


def patch(root, target):
    root = Path(root).resolve()
    if not (root / '.tournament-browser-port').is_file():
        raise ValueError('Refusing unmarked checkout: create .tournament-browser-port only in an isolated copy')
    version = json.loads((root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if (version['MajorVersion'], version['MinorVersion'], version['Changelist']) != (4, 15, 3228288):
        raise ValueError('This patch supports only the recovered UE4.15 CL3228288 source')
    sdk = root / 'Engine/Source/Programs/UnrealBuildTool/HTML5/HTML5SDKInfo.cs'
    backup = sdk.with_suffix('.cs.before-tournament-html5')
    current_sdk = sdk.read_text(encoding='utf-8-sig')
    text = backup.read_text(encoding='utf-8-sig') if backup.exists() else current_sdk
    if 'Tournament HTML5: explicit paths' not in text:
        begin = '\t\tpublic static string SetUpEmscriptenConfigFile()'
        finish = '\t\tpublic static string EmscriptenVersion()'
        if text.count(begin) != 1 or text.count(finish) != 1:
            raise ValueError('Unexpected Emscripten SDK implementation')
        start = text.index(begin)
        end = text.index(finish, start)
        updated_sdk = text[:start] + CONFIG_METHOD + text[end:]
    elif not backup.exists() and text.count(CONFIG_METHOD) == 1:
        updated_sdk = text  # Accept a complete pre-existing patch without rewriting it.
    else:
        raise ValueError('Original Emscripten SDK backup required')
    if current_sdk not in (text, updated_sdk):
        raise ValueError('Emscripten SDK source conflicts with backup')
    target_path = root / 'UnrealTournament/Source/TournamentBrowser.Target.cs'
    target_bytes = Path(target).read_bytes()
    # UE4.15 AutomationTool uses a dictionary keyed by target kind and crashes
    # with two Game targets. This isolated browser checkout has its own target;
    # preserve the desktop target as a non-discoverable backup for packaging.
    desktop = root / 'UnrealTournament/Source/UnrealTournament.Target.cs'
    saved = desktop.with_suffix('.cs.before-tournament-browser')
    if desktop.exists():
        if saved.exists():
            raise ValueError('Desktop target backup already exists; inspect before replacing')
    byte_order = root / 'Engine/Source/Runtime/Online/ICMP/Private/BrowserByteOrder.cpp'
    byte_order_bytes = Path(__file__).with_name('BrowserByteOrder.cpp').read_bytes()
    # Desktop unity builds incidentally supplied this declaration. The HTML5
    # unity grouping exposes the missing direct include in replay code.
    replay = root / 'Engine/Source/Runtime/Engine/Private/DemoNetDriver.cpp'
    text = replay.read_text(encoding='utf-8-sig')
    anchor = '#include "Engine/DemoNetDriver.h"'
    include = '#include "UnrealEngine.h"'
    replacement = anchor + '\n' + include
    if text.count(anchor) != 1 or text.count(include) > 1:
        raise ValueError('Unexpected replay include anchors')
    # Require real include lines; a comment must not satisfy the match guard.
    if text.splitlines().count(anchor) != 1:
        raise ValueError('Unexpected replay include layout')
    if include in text and (text.count(replacement) != 1 or text.splitlines().count(include) != 1):
        raise ValueError('Unexpected patched replay include layout')
    original_replay = text.replace(replacement, anchor) if include in text else text
    replay_backup = replay.with_suffix('.cpp.before-tournament-html5')
    if replay_backup.exists() and replay_backup.read_text(encoding='utf-8-sig') != original_replay:
        raise ValueError('Replay source conflicts with backup')
    updated_replay = original_replay.replace(anchor, replacement)
    for destination in (target_path, byte_order):
        if not destination.parent.is_dir() or destination.is_dir():
            raise ValueError(f'Unexpected destination: {destination}')

    # All input and backup checks pass before the first source change.
    if current_sdk != updated_sdk:
        if not backup.exists():
            shutil.copy2(sdk, backup)
        sdk.write_text(updated_sdk, encoding='utf-8-sig')
    for destination, contents in ((target_path, target_bytes), (byte_order, byte_order_bytes)):
        if not destination.exists() or destination.read_bytes() != contents:
            destination.write_bytes(contents)
    if desktop.exists():
        desktop.rename(saved)
    if text != updated_replay:
        if not replay_backup.exists():
            shutil.copy2(replay, replay_backup)
        replay.write_text(updated_replay, encoding='utf-8')
    print('Configured isolated legacy browser target and build-local Emscripten paths')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_root')
    args = parser.parse_args()
    patch(args.source_root, Path(__file__).with_name('TournamentBrowser.Target.cs'))
