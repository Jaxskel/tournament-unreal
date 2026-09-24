"""Desktop-browser WebGL fragment sampler compatibility; isolated checkout only.

Rebuild BOTH editor and ShaderCompileWorker ShaderFormatOpenGL modules, then
recook affected packages. Requires >=16 fragment, >=8 vertex and >=24 combined
texture units in the actual game context. Does not enable other ES3 features.
"""
import argparse
import json
from pathlib import Path
import shutil


def prepare(path, before, after):
    text = path.read_text(encoding='utf-8-sig')
    patched = text.count(after) == 1 and before not in text
    if not patched and (text.count(before) != 1 or after in text):
        raise ValueError(f'Unexpected shader source: {path.name}')
    original = text.replace(after, before) if patched else text
    backup = path.with_suffix(path.suffix + '.before-tournament-webgl')
    if backup.exists() and backup.read_text(encoding='utf-8-sig') != original:
        raise ValueError(f'Shader source conflicts with backup: {path.name}')
    return path, backup, text, original.replace(before, after)


def patch(root):
    root = Path(root).resolve()
    if not (root / '.tournament-browser-port').is_file():
        raise ValueError('Use the marked isolated browser port, with cooker stopped')
    version = json.loads((root / 'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if (version.get('MajorVersion'), version.get('MinorVersion'), version.get('Changelist')) != (4, 15, 3228288):
        raise ValueError('Unsupported engine revision')
    folder = root / 'Engine/Source/Developer/ShaderFormatOpenGL/Private'
    plans = [prepare(folder / 'OpenGLShaderCompiler.cpp',
        'const int32 MaxSamplers = GetMaxSamplers(Version);',
        '// Tournament desktop WebGL: preserve the eight-slot vertex budget.\n'
        '\tconst int32 MaxSamplers = (Version == GLSL_ES2_WEBGL && ShaderInput.Target.Frequency == SF_Pixel)\n'
        '\t\t? 16 : GetMaxSamplers(Version);'),
    prepare(folder / 'ShaderFormatOpenGL.cpp',
        'UE_SHADER_GLSL_ES2_VER_WEBGL = 61,',
        'UE_SHADER_GLSL_ES2_VER_WEBGL = 62, // Tournament fragment-sampler profile')]
    for path, backup, text, updated in plans:
        if updated != text:
            if not backup.exists():
                shutil.copy2(path, backup)
            path.write_text(updated, encoding='utf-8')
    print('Patched WebGL fragment sampler profile; rebuild editor AND worker, then recook')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source_root')
    patch(parser.parse_args().source_root)
