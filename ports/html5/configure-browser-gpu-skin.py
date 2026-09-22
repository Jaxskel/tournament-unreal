"""Explicit opt-in gate shared by native-editor and HTML5 build wrappers.

Default off: a previously patched tree is refused, never silently unpatched.
This records source inputs, not a successful build/cook/runtime validation.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
PATCHER=HERE/'patch-browser-gpu-skin.py'
PATCHER_SHA256='852f2a676cc670c1dc21e030aaac2a068248bb91345b8f0170425886eef9f5ea'

def load_patcher():
    if hashlib.sha256(PATCHER.read_bytes()).hexdigest()!=PATCHER_SHA256:
        raise ValueError('GPU skin candidate differs from reviewed source; review integration again')
    spec=importlib.util.spec_from_file_location('gpu_skin_candidate',PATCHER)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def root_path(root,module):
    root=module.physical(root)
    if not module.physical(root/'.tournament-browser-port').is_file():raise ValueError('Marked isolated root required')
    version=json.loads(module.physical(root/'Engine/Build/Build.version').read_text(encoding='utf-8-sig'))
    if tuple(version.get(k) for k in ('MajorVersion','MinorVersion','PatchVersion','Changelist'))!=(4,15,0,3228288):raise ValueError('Expected pinned UE4.15.0 CL3228288')
    return root

def configure(root,experimental=False,apply=False,phase='html5'):
    if phase not in ('html5','native-editor'):raise ValueError('Unknown build phase')
    module=load_patcher();root=root_path(root,module)
    items=[module.inspect(root,s) for s in module.SPECS]
    if not experimental and any(module.MARKER.encode() in i['source'] for i in items):
        raise ValueError('GPU skin experiment source already present: use -ExperimentalGpuSkin8 for BOTH builds or a separate unpatched checkout; default does not undo source')
    if apply and experimental:
        with contextlib.redirect_stdout(io.StringIO()):module.patch(root,apply=True)
        items=[module.inspect(root,s) for s in module.SPECS]
    return dict(schema=1,experiment='webgl-eight-influence-gpu-skin',enabled=bool(experimental),phase=phase,
                sourceApplied=bool(experimental and all(i['source']==i['updated'] for i in items)),
                status='source-inputs-only',validated=False,requiresFreshShaderCook=bool(experimental),
                requiresMatchingRuntimeAndPackage=bool(experimental),patcherSha256=PATCHER_SHA256,
                sources={str(s['path']):hashlib.sha256(i['source']).hexdigest() for s,i in zip(module.SPECS,items)},
                notice='No canonical promotion: compile editor/runtime with the same flag, fresh-cook matching permutations, then validate a private coherent pair.' if experimental else 'Experiment disabled; original pinned gate bodies confirmed.')

def editor_commands(root):
    root=Path(root);ubt=root/'Engine/Binaries/DotNET/UnrealBuildTool.exe';project=root/'UnrealTournament/UnrealTournament.uproject'
    # Full editor rebuild includes the Engine ShouldCache template registration;
    # rebuilding only ShaderFormatOpenGL would leave that caller's DLL stale.
    return [[str(ubt),'UnrealTournamentEditor','Win64','Development','-Project='+str(project),'-NoHotReload','-2015'],
            [str(ubt),'ShaderCompileWorker','Win64','Development','-Module','ShaderFormatOpenGL','-NoHotReload','-2015']]

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source_root');parser.add_argument('--experimental-gpu-skin8',action='store_true');parser.add_argument('--apply',action='store_true');parser.add_argument('--phase',choices=['html5','native-editor'],default='html5');parser.add_argument('--editor-plan',action='store_true');args=parser.parse_args()
    try:
        result=configure(args.source_root,args.experimental_gpu_skin8,args.apply,args.phase)
        if args.editor_plan:result['commands']=editor_commands(Path(args.source_root).absolute())
        print(json.dumps(result))
    except (ValueError,OSError,UnicodeError) as error:parser.exit(1,str(error)+'\n')
