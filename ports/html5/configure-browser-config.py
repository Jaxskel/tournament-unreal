"""Append the original browser-only engine settings to a marked local checkout."""
import argparse
import json
from pathlib import Path

MARKER_PREFIX = '; Tournament browser platform configuration'
MARKER = MARKER_PREFIX + ' v2'
# Freeze the exact released v1 block. Never derive an accepted migration source
# from the current template or overwrite an operator-modified/unknown block.
LEGACY_BLOCK = '''; Tournament browser platform configuration v1
; Merge these sections into the isolated project's Config/HTML5/HTML5Engine.ini.
; The game-engine subclass overrides Engine.GameEngine's inherited driver list.
[/Script/UnrealTournament.UTGameEngine]
-NetDriverDefinitions=(DefName="GameNetDriver",DriverClassName="OnlineSubsystemUtils.IpNetDriver",DriverClassNameFallback="OnlineSubsystemUtils.IpNetDriver")
+NetDriverDefinitions=(DefName="GameNetDriver",DriverClassName="/Script/HTML5Networking.WebSocketNetDriver",DriverClassNameFallback="/Script/HTML5Networking.WebSocketNetDriver")

[/Script/Engine.Engine]
BoneWeightMaterialName=/Engine/EngineMaterials/WorldGridMaterial.WorldGridMaterial

[Engine.StartupPackages]
-Package=/Engine/EngineDebugMaterials/BoneWeightMaterial
'''


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
    if MARKER_PREFIX in current:
        if current.count(MARKER_PREFIX) != 1:
            raise ValueError('Browser configuration changed; inspect before reapplying')
        if current.endswith(block):
            print('Browser configuration v2 already installed')
            return
        if not current.endswith(LEGACY_BLOCK):
            raise ValueError('Unknown or modified browser configuration block; inspect before migrating')
        # Replace only the exact v1 suffix; preserve the preceding configuration
        # and the existing original backup, including when no backup was needed.
        # Python's original Windows write_text emitted CRLF. Accept that exact
        # block as well as LF, without normalizing the operator's prefix bytes.
        raw = path.read_bytes()
        for newline in ('\r\n', '\n'):
            legacy = LEGACY_BLOCK.replace('\n', newline).encode('utf-8')
            if raw.endswith(legacy):
                path.write_bytes(raw[:-len(legacy)] + block.replace('\n', newline).encode('utf-8'))
                break
        else:
            raise ValueError('Modified browser configuration block line endings; inspect before migrating')
        print('Migrated browser configuration v1 to v2 (arrow material); restage before running')
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
