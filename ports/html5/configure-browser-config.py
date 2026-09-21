"""Append the original browser-only engine settings to a marked local checkout."""
import argparse
import json
from pathlib import Path

MARKER = '; Tournament browser platform configuration v1'


def configure(root):
    root = Path(root).resolve()
    if not (root / '.tournament-browser-port').is_file():
        raise ValueError('Use a marked isolated browser checkout')
    version = json.loads((root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if tuple(version.get(k) for k in ('MajorVersion', 'MinorVersion', 'Changelist')) != (4, 15, 3228288):
        raise ValueError('Unsupported engine revision')
    path = root / 'UnrealTournament/Config/HTML5/HTML5Engine.ini'
    settings = Path(__file__).with_name('config').joinpath('HTML5Engine.ini').read_text()
    block = MARKER + '\n' + settings
    current = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    if MARKER in current:
        if current.count(MARKER) != 1 or not current.endswith(block):
            raise ValueError('Browser configuration changed; inspect before reapplying')
        print('Browser configuration already installed')
        return
    # Refuse a competing subclass driver override instead of silently merging it.
    if '[/Script/UnrealTournament.UTGameEngine]' in current and 'NetDriverDefinitions=' in current:
        raise ValueError('Existing browser game driver configuration requires an explicit merge')
    backup = path.with_suffix('.ini.before-tournament-browser-config')
    if backup.exists() and backup.read_text(encoding='utf-8-sig') != current:
        raise ValueError('Conflicting browser configuration backup')
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not backup.exists():
        backup.write_bytes(path.read_bytes())
    path.write_text(current.rstrip() + '\n\n' + block, encoding='utf-8')
    print('Installed browser game packet driver and startup material settings; restage before running')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_root')
    configure(parser.parse_args().source_root)
