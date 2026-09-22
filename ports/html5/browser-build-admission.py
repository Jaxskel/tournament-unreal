"""Read-only Windows admission snapshot for an isolated browser source build.

Compilers block globally. Editors block when using the selected physical root,
or when executable/project ownership cannot be established. No process is killed.
This snapshot is not a lock or a guarantee against later process creation.
"""
import argparse
import ctypes
import importlib.util
import json
import ntpath
import os
from pathlib import Path
import re
import subprocess

COMPILERS=re.compile(r'^(clang\+\+|clang|llc|opt|llvm-link|link|cl|MSBuild|UnrealBuildTool|ShaderCompileWorker)\.exe$',re.I)
EDITORS={'ue4editor.exe','ue4editor-cmd.exe'}
PYTHON_DRIVERS=re.compile(r'^(py|python(?:w|[0-9.]+)?)\.exe$',re.I)

def normalize(path):
    if not isinstance(path,str) or not path or '\x00' in path or path.startswith(('\\\\?\\','\\\\.\\')):
        raise ValueError('Missing/ambiguous path')
    drive,tail=ntpath.splitdrive(path)
    if not drive or not tail.startswith(('\\','/')):raise ValueError('Path must be absolute with a drive/share')
    return ntpath.normcase(ntpath.normpath(path))

def within(path,root):
    return path==root or path.startswith(root.rstrip('\\')+'\\')

def windows_argv(command):
    if not isinstance(command,str) or not command.strip():raise ValueError('Missing command line')
    if os.name!='nt':raise ValueError('Windows argv decoding requires Windows')
    from ctypes import wintypes as W
    shell=ctypes.WinDLL('shell32',use_last_error=True);kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    shell.CommandLineToArgvW.argtypes=[W.LPCWSTR,ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype=ctypes.POINTER(W.LPWSTR)
    kernel.LocalFree.argtypes=[W.HLOCAL];kernel.LocalFree.restype=W.HLOCAL
    count=ctypes.c_int();pointer=shell.CommandLineToArgvW(command,ctypes.byref(count))
    if not pointer:raise ctypes.WinError(ctypes.get_last_error())
    try:return [pointer[i] for i in range(count.value)]
    finally:kernel.LocalFree(ctypes.cast(pointer,W.HLOCAL))

def editor_reason(root,process,physical,decode=windows_argv):
    """Return None only when executable AND explicit project are known foreign."""
    try:
        selected=normalize(root);exe=normalize(process.get('ExecutablePath'))
        physical(process['ExecutablePath'],False)
        if ntpath.basename(exe)!=str(process.get('Name','')).lower():raise ValueError('Executable/name mismatch')
        if within(exe,selected):return 'editor executable uses selected root'
        suffix='\\engine\\binaries\\win64\\'+ntpath.basename(exe)
        if not exe.endswith(suffix):raise ValueError('Unrecognized editor installation layout')
        foreign_root=exe[:-len(suffix)]
        physical(foreign_root,True)
        physical(ntpath.join(foreign_root,'Engine','Build','Build.version'),False)
        args=decode(process.get('CommandLine'))
        if not args or normalize(args[0])!=exe:raise ValueError('Ambiguous executable command line')
        projects=[];i=1
        while i<len(args):
            arg=args[i];lower=arg.lower()
            if lower in ('-project','/project'):
                i+=1
                if i==len(args):raise ValueError('Missing project argument')
                projects.append(args[i])
            elif lower.startswith(('-project=','/project=')):projects.append(arg.split('=',1)[1])
            elif lower.endswith('.uproject'):projects.append(arg)
            i+=1
        if not projects:raise ValueError('No explicit project ownership evidence')
        normalized=set()
        for project in projects:
            candidate=normalize(project)
            if not candidate.endswith('.uproject'):raise ValueError('Unexpected project path')
            physical(project,False)
            if within(candidate,selected):return 'editor project uses selected root'
            # A cross-install project might load plugins/modules from another
            # tree. Permit only the positively identified same foreign root.
            if not within(candidate,foreign_root):raise ValueError('Project belongs to an unverified third root')
            normalized.add(candidate)
        if len(normalized)!=1:raise ValueError('Multiple project references')
        return None
    except (ValueError,OSError,TypeError) as error:
        return 'editor ownership unknown: '+str(error)

def blockers(root,processes,physical,decode=windows_argv):
    normalize(root);result=[]
    for process in processes:
        if not isinstance(process,dict) or not isinstance(process.get('Name'),str) or not process['Name']:
            raise ValueError('Incomplete process inventory record')
        name=process['Name']
        command=process.get('CommandLine') or ''
        reason=None
        if COMPILERS.fullmatch(name) or re.search(r'\bemcc(?:\.py)?\s',command,re.I):reason='compiler active (global guard)'
        elif PYTHON_DRIVERS.fullmatch(name):
            # A Python driver can be alive between clang/llc subprocesses. Use
            # actual Windows argv so a quoted emcc.py path cannot escape the
            # global compiler guard. Unreadable driver intent fails closed.
            try:
                args=decode(command)
                if not args or not all(isinstance(arg,str) for arg in args):
                    raise ValueError('Missing Python argv')
                if any(ntpath.basename(arg).lower() in ('emcc','emcc.py') for arg in args[1:]):
                    reason='emcc Python driver active (global guard)'
            except (ValueError,OSError,TypeError) as error:
                reason='Python driver command line unknown: '+str(error)
        elif name.lower() in EDITORS:reason=editor_reason(root,process,physical,decode)
        if reason:result.append(dict(pid=process.get('ProcessId'),name=name,reason=reason))
    return result

def check(root):
    if os.name!='nt':raise ValueError('Admission inventory requires Windows')
    spec=importlib.util.spec_from_file_location('gpu_config',Path(__file__).with_name('configure-browser-gpu-skin.py'))
    config=importlib.util.module_from_spec(spec);spec.loader.exec_module(config)
    module=config.load_patcher();root=config.root_path(root,module)
    def physical(path,directory):
        candidate=module.physical(Path(path))
        if (candidate.is_dir() if directory else candidate.is_file()) is not True:raise ValueError('Unexpected physical path kind')
    command='[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); @((Get-CimInstance Win32_Process) | Select-Object Name,ProcessId,ExecutablePath,CommandLine) | ConvertTo-Json -Depth 3 -Compress'
    output=subprocess.run(['powershell','-NoProfile','-NonInteractive','-Command',command],capture_output=True,text=True,encoding='utf-8',errors='strict',timeout=30,check=True)
    processes=json.loads(output.stdout.lstrip('\ufeff'))
    if not isinstance(processes,list) or not processes:raise ValueError('Missing process inventory')
    found=blockers(str(root),processes,physical)
    if found:raise ValueError('Source freeze admission blocked: '+json.dumps(found))
    foreign=[dict(pid=p.get('ProcessId'),name=p['Name'],executable=p.get('ExecutablePath')) for p in processes if p['Name'].lower() in EDITORS]
    return dict(status='clear-snapshot',root=str(root),processesInspected=len(processes),foreignEditors=foreign,lock=False)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('source_root');args=parser.parse_args()
    try:print(json.dumps(check(args.source_root)))
    except (ValueError,OSError,subprocess.SubprocessError,UnicodeError) as error:parser.exit(1,str(error)+'\n')
