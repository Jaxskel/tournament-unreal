"""Remove the desktop busy-wait from browser callbacks, preserving native pacing.

LaunchHTML5 already schedules one engine tick per requestAnimationFrame. In the
matching engine, HTML5 SleepNoStats is a no-op, so the desktop cap spins on the
browser thread. Do not replace RAF with a timer or alter simulation delta time.
"""
import argparse
import json
from pathlib import Path
import shutil


def patch(root):
    root = Path(root).resolve()
    if not (root / '.tournament-browser-port').is_file():
        raise ValueError('Use only a marked isolated browser checkout')
    version = json.loads((root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if (version['MajorVersion'], version['MinorVersion'], version['Changelist']) != (4, 15, 3228288):
        raise ValueError('Unsupported engine revision')
    launch = (root / 'Engine/Source/Runtime/Launch/Private/HTML5/LaunchHTML5.cpp').read_text(encoding='utf-8-sig')
    if 'emscripten_set_main_loop(HTML5_Tick, 0, true)' not in launch:
        raise ValueError('Expected requestAnimationFrame-driven engine loop')
    path = root / 'Engine/Source/Runtime/Engine/Private/UnrealEngine.cpp'
    before = 'const float MaxTickRate = FABTest::StaticIsActive() ? 0.0f : (bUseFixedFrameRate ? FixedFrameRate : GivenMaxTickRate);'
    after = ('// Tournament browser: RAF owns pacing; HTML5 SleepNoStats cannot yield.\n'
             '#if defined(PLATFORM_HTML5_BROWSER) && PLATFORM_HTML5_BROWSER\n'
             '\t\tconst float MaxTickRate = 0.0f;\n'
             '#else\n\t\t' + before + '\n#endif')
    text = path.read_text(encoding='utf-8-sig')
    if after in text:
        print('Browser pacing already configured')
        return
    if text.count(before) != 1:
        raise ValueError('Unexpected engine pacing implementation')
    saved = path.with_suffix('.cpp.before-tournament-pacing')
    if not saved.exists():
        shutil.copy2(path, saved)
    path.write_text(text.replace(before, after), encoding='utf-8')
    print('Browser callbacks no longer busy-wait; rebuild the browser engine')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_root')
    patch(parser.parse_args().source_root)
