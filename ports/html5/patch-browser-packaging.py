"""Keep desktop tutorial movies out of the browser arena asset archive.

The legacy file packager also supports filesystem backing outside the fixed Wasm
heap. Use that instead of permanently copying the entire compressed pak into it.
Recompile AutomationTool scripts and restage after applying this isolated patch.
"""
import argparse
import json
from pathlib import Path
import shutil


def patch(root):
    root = Path(root).resolve()
    if not (root / '.tournament-browser-port').is_file():
        raise ValueError('Use only the isolated browser checkout')
    version = json.loads((root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if (version['MajorVersion'], version['MinorVersion'], version['Changelist']) != (4, 15, 3228288):
        raise ValueError('Unsupported engine revision')
    path = root / 'Engine/Source/Programs/AutomationTool/HTML5/HTML5Platform.Automation.cs'
    text = path.read_text(encoding='utf-8-sig')
    marker = '// Tournament arena browser packaging'
    declaration = 'public class HTML5Platform : Platform\n{'
    preload = '--preload . --js-output='
    patched_declaration = declaration + '\n\t' + marker + '\n' + '\tpublic override bool StageMovies { get { return false; } }\n'
    patched_preload = '--no-heap-copy ' + preload
    patched = marker in text or '--no-heap-copy' in text or 'StageMovies' in text
    if patched and (text.count(patched_declaration) != 1
                    or text.count(patched_preload) != 1
                    or text.count(marker) != 1 or text.count('StageMovies') != 1
                    or text.count('--no-heap-copy') != 1):
        raise ValueError('Incomplete or duplicate browser packaging patch')
    original = text.replace(patched_declaration, declaration).replace(patched_preload, preload) if patched else text
    if original.count(declaration) != 1 or original.count(preload) != 1:
        raise ValueError('Unexpected HTML5 AutomationTool implementation')
    saved = path.with_suffix('.cs.before-tournament-packaging')
    if saved.exists() and saved.read_text(encoding='utf-8-sig') != original:
        raise ValueError('HTML5 packaging source conflicts with backup')
    if patched:
        return
    if not saved.exists():
        shutil.copy2(path, saved)
    text = text.replace(declaration, patched_declaration)
    text = text.replace(preload, patched_preload)
    path.write_text(text, encoding='utf-8-sig')
    print('Browser movies excluded; filesystem archive stays outside fixed heap. Recompile UAT and restage.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_root')
    patch(parser.parse_args().source_root)
