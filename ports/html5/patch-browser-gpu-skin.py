"""Candidate eight-influence WebGL skinning; local review only until mesh evidence.

Read-only by default. Two pinned UE4.15 CL3228288 method bodies, physical isolated
root and exact original backups required. Native platforms retain their gates.
Does not alter weights, bones, shader code or the 75-bone ES2 palette limit.
Requires fresh WebGL shader permutations plus runtime/animation validation;
source transformation and host-compiled stub tests do not establish GPU support.
No cloth parity claim. No build/cook/wrapper integration is performed here.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

MARKER = 'TOURNAMENT_BROWSER_GPU_SKIN_V1'
BACKUP_SUFFIX = '.before-tournament-browser-gpu-skin-v1'
INCLUDE_ANCHOR = '#include "GPUSkinVertexFactory.h"'
INCLUDE = '// ' + MARKER + '_INCLUDE\n#if PLATFORM_HTML5_BROWSER\n#include <emscripten/emscripten.h>\n#endif\n'
# Matching legacy runtime GL.makeContextCurrent assigns Module.ctx=context.GLctx.
# Query the current game context, never create or cache a separate one. Unknown
# capability is CPU fallback. These conservative values match the captured GPU;
# they are not a universal minimum or proof a shader permutation will link.
CAPABILITY_JS = '''try {
    var ctx = Module.ctx;
    if (!ctx || ctx.canvas !== Module.canvas || typeof ctx.getParameter !== 'function' ||
        typeof ctx.isContextLost !== 'function' || ctx.isContextLost()) return 0;
    var attributes = ctx.getParameter(ctx.MAX_VERTEX_ATTRIBS);
    var uniforms = ctx.getParameter(ctx.MAX_VERTEX_UNIFORM_VECTORS);
    return typeof attributes === 'number' && isFinite(attributes) && attributes >= 16 &&
        typeof uniforms === 'number' && isFinite(uniforms) && uniforms >= 1024 ? 1 : 0;
} catch (error) { return 0; }'''
RUNTIME_OLD = 'return (MaxBonesPerChunk > MaxGPUSkinBones) || (HasExtraBoneInfluences() && FeatureLevel < ERHIFeatureLevel::ES3_1);'
RUNTIME_NEW = '''// TOURNAMENT_BROWSER_GPU_SKIN_V1
#if PLATFORM_HTML5_BROWSER
    if (MaxBonesPerChunk > MaxGPUSkinBones) return true;
    if (HasExtraBoneInfluences() && FeatureLevel < ERHIFeatureLevel::ES3_1)
    {
        return !EM_ASM_INT({
CAPABILITY
        });
    }
    return false;
#else
    ORIGINAL
#endif'''.replace('CAPABILITY', '\n'.join('            '+line for line in CAPABILITY_JS.splitlines())).replace('ORIGINAL', RUNTIME_OLD)
CACHE_OLD = 'if (bExtraBoneInfluencesT && GetMaxSupportedFeatureLevel(Platform) < ERHIFeatureLevel::ES3_1)'
CACHE_NEW = '// '+MARKER+'\n\t'+CACHE_OLD[:-1]+' && Platform != SP_OPENGL_ES2_WEBGL)'
SPECS = (
 dict(name='runtime', path=Path('Engine/Source/Runtime/Engine/Private/SkeletalMesh.cpp'),
      signature='bool FSkeletalMeshResource::RequiresCPUSkinning(ERHIFeatureLevel::Type FeatureLevel) const',
      body_sha256='4e542bf79222bba45aa5b618a637d408d5a0ca302b7fdb37c3d008b35fdf850d', old=RUNTIME_OLD, new=RUNTIME_NEW),
 dict(name='cache', path=Path('Engine/Source/Runtime/Engine/Private/GPUSkinVertexFactory.cpp'),
      signature='bool TGPUSkinVertexFactory<bExtraBoneInfluencesT>::ShouldCache(EShaderPlatform Platform, const class FMaterial* Material, const FShaderType* ShaderType)',
      body_sha256='56cf090ad61470e54753dca39255287c662473600af78e27e7c685880bdbb432', old=CACHE_OLD, new=CACHE_NEW),
)

def digest(data): return hashlib.sha256(data).hexdigest()

def scan(text):
    return re.sub(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\r\n]*|/\*[\s\S]*?\*/',
                  lambda m: re.sub(r'[^\r\n]', ' ', m.group()), text)

def body_span(text, spec):
    code=scan(text)
    matches=list(re.finditer(re.escape(spec['signature'])+r'\s*\{',code))
    if len(matches)!=1: raise ValueError('Expected one inspected method: '+spec['name'])
    start=matches[0].end()-1; depth=0
    for end in range(start,len(code)):
        if code[end]=='{': depth+=1
        elif code[end]=='}':
            depth-=1
            if depth==0:return start,end+1
    raise ValueError('Unclosed method')

def transform(data,spec):
    encoding='utf-8-sig' if data.startswith(b'\xef\xbb\xbf') else 'utf-8'
    text=data.decode(encoding); nl='\r\n' if '\r\n' in text else '\n'
    if nl=='\r\n' and '\n' in text.replace('\r\n',''):raise ValueError('Mixed line endings')
    normalized=text.replace('\r\n','\n'); marked=MARKER in normalized
    clean=normalized
    if marked:
        if clean.count(spec['new'])!=1:raise ValueError('Altered candidate block')
        clean=clean.replace(spec['new'],spec['old'],1)
        if spec['name']=='runtime':
            if clean.count(INCLUDE)!=1:raise ValueError('Missing or altered browser include')
            clean=clean.replace(INCLUDE,'',1)
        if MARKER in clean:raise ValueError('Misplaced or duplicate candidate marker')
    start,end=body_span(clean,spec);body=clean[start:end]
    if digest(body.encode())!=spec['body_sha256']:raise ValueError('Method differs from inspected pinned body')
    if body.count(spec['old'])!=1:raise ValueError('Missing gate')
    out=clean[:start]+body.replace(spec['old'],spec['new'],1)+clean[end:]
    if spec['name']=='runtime':
        if clean.count(INCLUDE_ANCHOR)!=1:raise ValueError('Unexpected include boundary')
        out=out.replace(INCLUDE_ANCHOR+'\n',INCLUDE_ANCHOR+'\n'+INCLUDE,1)
        if INCLUDE not in out:raise ValueError('Missing include newline')
    if marked and normalized!=out:raise ValueError('Misplaced candidate block')
    return out.replace('\n',nl).encode(encoding)

def physical(path,missing=False):
    path=Path(os.path.abspath(path))
    for item in [*reversed(path.parents),path]:
        try:info=item.lstat()
        except FileNotFoundError:
            if missing and item==path:return path
            raise ValueError('Missing physical path: '+str(item))
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise ValueError('Linked/reparse path refused')
        if stat.S_ISREG(info.st_mode):
            if item!=path or info.st_nlink!=1:raise ValueError('Shared file/non-directory ancestor refused')
        elif not stat.S_ISDIR(info.st_mode):raise ValueError('Special path refused')
    return path

def inspect(root,spec):
    path=physical(root/spec['path']);original=path.read_bytes();updated=transform(original,spec)
    backup=physical(Path(str(path)+BACKUP_SUFFIX),True)
    saved=backup.read_bytes() if backup.exists() else None
    if saved is not None:
        if MARKER.encode() in saved or transform(saved,spec)!=updated:raise ValueError('Conflicting original backup')
        if original!=updated and original!=saved:raise ValueError('Original backup does not match source')
    elif original==updated:raise ValueError('Patched state requires original backup')
    return dict(path=path,source=original,updated=updated,backup=backup,saved=saved)

def recheck(item):
    physical(item['path']);physical(item['backup'],True)
    if item['path'].read_bytes()!=item['source']:raise ValueError('Source changed since preflight')
    saved=item['backup'].read_bytes() if item['backup'].exists() else None
    if saved!=item['saved']:raise ValueError('Backup changed since preflight')

def patch(root,apply=False):
    root=physical(root)
    if not physical(root/'.tournament-browser-port').is_file():raise ValueError('Isolated root marker required')
    version=json.loads(physical(root/'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if tuple(version.get(k) for k in ('MajorVersion','MinorVersion','PatchVersion','Changelist'))!=(4,15,0,3228288):raise ValueError('Expected UE4.15.0 CL3228288')
    items=[inspect(root,s) for s in SPECS] # Both sources and backups before any write.
    for item in items:recheck(item)
    if apply:
        for item in items:
            if item['saved'] is None:
                with item['backup'].open('xb') as stream:stream.write(item['source'])
                item['saved']=item['source']
        for item in items:recheck(item)
        for item in items:
            if item['source']==item['updated']:continue
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(dir=item['path'].parent,prefix='.gpu-skin-',delete=False) as stream:
                    temporary=Path(stream.name);stream.write(item['updated'])
                recheck(item)
                os.chmod(temporary,stat.S_IMODE(item['path'].stat().st_mode))
                os.replace(temporary,item['path'])
            finally:
                if temporary is not None and temporary.exists():temporary.unlink()
    result=dict(status='patched' if apply else 'preflight',candidate=True,files=[dict(path=str(s['path']),changed=i['source']!=i['updated'],sha256=digest(i['updated'])) for s,i in zip(SPECS,items)])
    print(json.dumps(result));return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source_root');parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    try:patch(args.source_root,args.apply)
    except (ValueError,OSError,UnicodeError) as error:parser.exit(1,str(error)+'\n')
