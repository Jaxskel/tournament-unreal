#!/usr/bin/env python3
"""Prepare a bounded, private UE4 content tree. Planning is the default.

No hardlinks, engine builds, process termination, recursive junction deletion, or
source writes. Windows execution only; pure planning/validation is testable elsewhere.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys

ROBOT_MATERIALS = "/Game/RestrictedAssets/Character/Robot/Materials/"
ROBOT_PACKAGES = {ROBOT_MATERIALS + n for n in (
    "M_86D_Robot_Head", "M_86D_Robot_Legs", "M_86D_Robot_Visor")}
PACKAGE = re.compile(r"^/Game/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_-]+$")
HERE = Path(__file__).absolute().parent
SUPPORT_DIRS = ("Config", "Source", "Binaries", "Build", "Plugins")


class Unsafe(ValueError):
    pass


def sha1(path: Path) -> str:
    digest = hashlib.sha1()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_reparse(path: Path) -> bool:
    info = path.lstat()
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, "st_file_attributes", 0) & 0x400)


def inside(path: Path, root: Path) -> bool:
    # Callers choose lexical absolute paths or resolved paths explicitly.
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def physical(path: Path, *, allow_missing: bool = False) -> Path:
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if not os.path.lexists(part):
            if allow_missing:
                continue
            raise Unsafe(f"Missing path: {part}")
        if is_reparse(part):
            raise Unsafe(f"Refusing reparse/symlink path: {part}")
    if path.is_file() and path.stat().st_nlink != 1:
        raise Unsafe(f"Refusing hardlinked output/marker: {path}")
    return path


def load_manifest(path: Path) -> tuple[dict, list[str], set[str]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if type(data.get("schema")) is not int or data["schema"] != 1:
        raise Unsafe("Expected manifest schema 1")
    if not isinstance(data.get("meshes"), list) or not all(isinstance(p, str) for p in data["meshes"]):
        raise Unsafe("meshes must be an array of object paths")
    if not isinstance(data.get("assets"), list):
        raise Unsafe("assets must be an array")
    packages, seen, new = [], set(), set()
    for entry in data["assets"]:
        if not isinstance(entry, dict):
            raise Unsafe("Each asset must be an object")
        package = entry.get("package", "")
        if not isinstance(package, str) or not PACKAGE.fullmatch(package):
            raise Unsafe(f"Invalid package: {package!r}")
        operation = entry.get("operation")
        texture, parameter = entry.get("diffuse_texture", ""), entry.get("source_parameter", "")
        parent = entry.get("fallback_parent", "")
        if not all(isinstance(v, str) for v in (texture, parameter, parent)):
            raise Unsafe("Texture, parameter and parent must be strings")
        tint = entry.get("tint", [1, 1, 1])
        if not isinstance(tint, list) or len(tint) != 3 or any(type(v) not in (int, float) or not 0 <= v <= 1 for v in tint):
            raise Unsafe("tint must contain three finite numbers in [0,1]")
        if entry.get("shading", "default_lit") not in ("default_lit", "unlit"):
            raise Unsafe("shading must be default_lit or unlit")
        if operation == "repair_robot":
            if package not in ROBOT_PACKAGES or texture or parameter or parent:
                raise Unsafe("repair_robot is restricted to the three Robot material packages")
        elif operation == "fallback_textured":
            if not texture.startswith(("/Game/", "/Engine/")) or "." not in texture or ".." in texture:
                raise Unsafe("fallback_textured requires an explicit diffuse_texture object path")
        elif operation == "fallback_color_experimental":
            if entry.get("experimental") is not True or texture or parameter or max(tint) <= 0:
                raise Unsafe("Color fallback requires experimental=true, visible tint, and no texture/parameter")
        else:
            raise Unsafe(f"Unknown operation: {operation}")
        for value in (package, *([parent] if parent else [])):
            if not PACKAGE.fullmatch(value) or value.casefold() in seen:
                raise Unsafe(f"Invalid or duplicate package: {value}")
            seen.add(value.casefold())
            packages.append(value)
        if parent:
            if not parent.startswith("/Game/HTML5Compat/"):
                raise Unsafe("fallback_parent must be a unique /Game/HTML5Compat/ package")
            new.add(parent)
    return data, packages, new


def relative_asset(package: str) -> Path:
    if not PACKAGE.fullmatch(package):
        raise Unsafe(f"Invalid package: {package}")
    return Path(*PurePosixPath(package[6:] + ".uasset").parts)


def sparse_plan(source: Path, mutable: list[Path], trusted_root: Path) -> list[dict]:
    """Expand only selected ancestors; junction unrelated directory subtrees.

    Loose sibling files are real copies, so no file-symlink privilege is needed.
    Refuse source reparse files and directory targets outside the declared original.
    """
    operations = []

    def visit(relative: Path, pending: list[Path]) -> None:
        operations.append({"kind": "mkdir", "relative": relative})
        current = source / relative
        children = {p.name: p for p in current.iterdir()} if current.exists() else {}
        needed = {p.parts[0] for p in pending if len(p.parts) > 1}
        # Windows case-insensitive names: do not generate a second differently-cased directory.
        folded = {name.casefold(): name for name in children}
        for name in needed:
            existing = folded.get(name.casefold())
            if existing and existing != name:
                raise Unsafe(f"Use source spelling in manifest: {current / existing}, not {name}")
        for name in sorted(set(children) | needed):
            src = children.get(name, current / name)
            dst_rel = relative / name
            descendants = [Path(*p.parts[1:]) for p in pending if len(p.parts) > 1 and p.parts[0] == name]
            if name in needed:
                if src.exists() and not src.is_dir():
                    raise Unsafe(f"Expected source directory: {src}")
                if src.exists() and not inside(src.resolve(), trusted_root):
                    raise Unsafe(f"Source escapes original root: {src}")
                visit(dst_rel, descendants)
            elif src.is_dir():
                target = src.resolve()
                if not inside(target, trusted_root):
                    raise Unsafe(f"Junction source escapes original root: {src}")
                operations.append({"kind": "junction", "relative": dst_rel, "source": target})
            elif src.is_file():
                if is_reparse(src) or not inside(src.resolve(), trusted_root):
                    raise Unsafe(f"Refusing redirected source file: {src}")
                operations.append({"kind": "copy", "relative": dst_rel, "source": src, "bytes": src.stat().st_size})
            else:
                raise Unsafe(f"Unexpected source entry: {src}")
    visit(Path(), mutable)
    return operations


def tree_plan(source: Path, destination: Path) -> list[tuple[Path, Path]]:
    """Copy only named project support trees, rejecting nested reparse points."""
    files = []
    if not source.exists():
        return files
    physical(source)
    for current, dirs, names in os.walk(source, followlinks=False):
        current = Path(current)
        for name in dirs + names:
            child = current / name
            if is_reparse(child):
                raise Unsafe(f"Support tree has a reparse point; prepare an explicit private copy instead: {child}")
        for name in names:
            child = current / name
            files.append((child, destination / child.relative_to(source)))
    return files


def matching_plugin(installed: Path) -> bool:
    if not installed.exists():
        return False
    physical(installed)
    for src, dst in tree_plan(HERE / "UT4Html5Compat", installed):
        physical(dst)
        if not dst.is_file() or sha1(src) != sha1(dst):
            raise Unsafe(f"Installed compatibility source differs; coordinate versions before preparation: {dst}")
    return True


def copy_new(source: Path, destination: Path) -> None:
    physical(destination.parent, allow_missing=True)
    if os.path.lexists(destination):
        raise Unsafe(f"Refusing overwrite: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # copyfile creates a fresh inode; never copy a hardlink or a read-only source mode.
    with source.open("rb") as src, destination.open("xb") as dst:
        shutil.copyfileobj(src, dst, 1024 * 1024)
    physical(destination)


def create_junction(destination: Path, target: Path) -> None:
    # Avoid cmd.exe expansion and interpolation of user paths.
    env = dict(os.environ, UT4_COW_LINK=str(destination), UT4_COW_TARGET=str(target))
    result = subprocess.run([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "$ErrorActionPreference='Stop'; New-Item -ItemType Junction -Path $env:UT4_COW_LINK -Target $env:UT4_COW_TARGET | Out-Null"
    ], env=env, capture_output=True, text=True)
    if result.returncode:
        raise Unsafe(f"Junction creation failed: {destination}: {result.stderr.strip()}")
    if not is_reparse(destination) or destination.resolve() != target.resolve():
        raise Unsafe(f"Junction verification failed: {destination}")


def ensure_idle(roots: list[Path]) -> None:
    result = subprocess.run([
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        "$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process | Where-Object {$_.Name -match '^(UE4Editor.*|ShaderCompileWorker|UnrealBuildTool|UnrealHeaderTool)\\.exe$'} | Select-Object ProcessId,Name,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"
    ], capture_output=True, text=True)
    if result.returncode:
        raise Unsafe("Cannot establish process idleness: " + result.stderr.strip())
    rows = json.loads(result.stdout or "[]")
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        evidence = str(row.get("ExecutablePath") or "") + " " + str(row.get("CommandLine") or "")
        if not evidence.strip() or any(str(root).casefold() in evidence.casefold() for root in roots):
            raise Unsafe(f"Relevant editor/build process still running: {row['Name']} PID {row['ProcessId']}; nothing was stopped")


def audit(receipt_path: Path) -> None:
    physical(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    for row in receipt["copied_content_files"]:
        if sha1(Path(row["source"])) != row["sha1"]:
            raise Unsafe(f"Original changed: {row['source']}")
        if not row["mutable"]:
            physical(Path(row["file"]))
            if sha1(Path(row["file"])) != row["sha1"]:
                raise Unsafe(f"Unselected private sibling changed: {row['file']}")
    for row in receipt["files"]:
        physical(Path(row["file"]), allow_missing=row["new"])
    print("AUDIT PASS: copied originals unchanged; unselected copied siblings unchanged; save paths physical")


def prepare(args: argparse.Namespace) -> dict:
    isolated = physical(Path(args.isolated_root))
    marker = physical(isolated / ".tournament-browser-port")
    if not marker.is_file():
        raise Unsafe("The isolated port marker must be a regular file")
    project = physical(Path(args.project))
    if not inside(project, isolated) or project.suffix.lower() != ".uproject":
        raise Unsafe("Project must be a physical .uproject inside the marked isolated root")
    original = physical(Path(args.original_root))
    if inside(isolated, original) or inside(original, isolated):
        raise Unsafe("Original and isolated roots must be disjoint")
    content = project.parent / "Content"
    if not is_reparse(content) or getattr(content.lstat(), "st_reparse_tag", None) != 0xA0000003:
        raise Unsafe("Input Content must be a Windows directory JUNCTION; existing physical overlays are never overwritten")
    source = content.resolve()
    if not source.is_dir() or not inside(source, original):
        raise Unsafe("Content junction must resolve inside the explicitly declared original root")
    manifest_path = Path(args.manifest).absolute()
    _, packages, new = load_manifest(manifest_path)
    if not packages:
        raise Unsafe("COW preparation requires at least one explicitly selected asset")
    relative = [relative_asset(p) for p in packages]
    for package, rel in zip(packages, relative):
        src = source / rel
        if package in new:
            if src.exists():
                raise Unsafe(f"Fallback parent must be new: {package}")
        elif not src.is_file():
            raise Unsafe(f"Selected package missing: {src}")
    operations = sparse_plan(source, relative, original)
    if args.mode == "shadow":
        if not args.shadow_project_dir:
            raise Unsafe("shadow mode requires --shadow-project-dir")
        target_project = physical(Path(args.shadow_project_dir), allow_missing=True)
        if os.path.lexists(target_project) or inside(target_project, original) or inside(target_project, isolated):
            raise Unsafe("Shadow directory must be new and outside original and isolated roots")
        backup = None
        target_content = target_project / "Content"
        stage = target_content
    else:
        target_project = project.parent
        target_content = content
        stage = target_project / "Content.compat-staging"
        backup = target_project / "Content.compat-original-junction"
        for path in (stage, backup):
            if os.path.lexists(path):
                raise Unsafe(f"Existing staging/backup requires manual inspection: {path}")
    receipt_path = target_project / "html5-compat-cow.json"
    physical(receipt_path, allow_missing=True)
    if receipt_path.exists():
        raise Unsafe("Existing receipt is never overwritten")
    support = []
    if args.mode == "shadow":
        support.append((project, target_project / project.name))
        for directory in SUPPORT_DIRS:
            support.extend(tree_plan(project.parent / directory, target_project / directory))
    plugin_destination = target_project / "Plugins" / "UT4Html5Compat"
    physical(plugin_destination, allow_missing=True)
    # Report may already have been built/run in the isolated project. Preserve
    # identical installed source and its matching binaries rather than overwrite it.
    installed = matching_plugin(project.parent / "Plugins" / "UT4Html5Compat")
    if not installed:
        support.extend(tree_plan(HERE / "UT4Html5Compat", plugin_destination))
    copied_bytes = sum(op.get("bytes", 0) for op in operations) + sum(src.stat().st_size for src, _ in support)
    if copied_bytes > args.max_copy_mib * 1024 * 1024:
        raise Unsafe(f"Copy budget exceeded: {copied_bytes} bytes; inspect the plan before increasing --max-copy-mib")
    summary = {
        "mode": args.mode, "project": str(target_project / project.name), "content_source": str(source),
        "content_destination": str(target_content), "backup_junction": str(backup) if backup else None,
        "receipt": str(receipt_path), "copy_bytes": copied_bytes,
        "content_copies": sum(op["kind"] == "copy" for op in operations),
        "content_junctions": sum(op["kind"] == "junction" for op in operations),
        "allowlisted_packages": packages, "execute": args.execute,
    }
    print(json.dumps(summary, indent=2))
    if not args.execute:
        return summary
    if os.name != "nt":
        raise Unsafe("Execution is Windows-only")
    ensure_idle([isolated, target_project])
    # All inputs and size limits have been validated before the first write.
    target_project.mkdir(parents=True, exist_ok=True)
    copied = []
    for op in operations:
        destination = stage / op["relative"]
        if op["kind"] == "mkdir":
            physical(destination, allow_missing=True)
            destination.mkdir(parents=True, exist_ok=False)
        elif op["kind"] == "junction":
            create_junction(destination, op["source"])
        else:
            copy_new(op["source"], destination)
            digest = sha1(destination)
            if digest != sha1(op["source"]):
                raise Unsafe(f"Source changed while copying: {op['source']}")
            copied.append({"source": str(op["source"]), "file": str(target_content / op["relative"]),
                           "sha1": digest, "mutable": op["relative"] in relative})
    for src, dst in support:
        copy_new(src, dst)
    receipt = {
        "schema": 1, "mode": args.mode, "manifest_sha1": sha1(manifest_path),
        "project_dir": str(target_project), "content_root": str(target_content), "original_root": str(original),
        "backup_junction": str(backup) if backup else None,
        "files": [{"package": p, "file": str(target_content / relative_asset(p)), "new": p in new} for p in packages],
        "copied_content_files": copied,
    }
    if args.mode == "inplace":
        # Recheck immediately before mutation. Rename the junction itself, never its target.
        ensure_idle([isolated])
        if not is_reparse(content) or content.resolve() != source or getattr(content.lstat(), "st_reparse_tag", None) != 0xA0000003:
            raise Unsafe("Content junction changed during preparation")
        os.rename(content, backup)
        try:
            os.rename(stage, content)
        except BaseException:
            os.rename(backup, content)
            raise
    # Deliberately no recursive cleanup on failures: staged trees contain junctions.
    with receipt_path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, indent=2)
        stream.write("\n")
    audit(receipt_path)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audit", type=Path, help="Read-only original/sibling hash and physical-output audit")
    parser.add_argument("--mode", choices=("inplace", "shadow"), default="shadow")
    parser.add_argument("--project")
    parser.add_argument("--isolated-root")
    parser.add_argument("--original-root")
    parser.add_argument("--manifest")
    parser.add_argument("--shadow-project-dir")
    parser.add_argument("--max-copy-mib", type=int, default=2048)
    parser.add_argument("--execute", action="store_true", help="Actually create files/junctions; otherwise only plan")
    args = parser.parse_args()
    try:
        if args.audit:
            audit(args.audit)
        else:
            if not all((args.project, args.isolated_root, args.original_root, args.manifest)):
                parser.error("--project, --isolated-root, --original-root and --manifest are required")
            if args.max_copy_mib <= 0:
                raise Unsafe("Copy budget must be positive")
            prepare(args)
    except (Unsafe, OSError, ValueError, KeyError) as error:
        print(f"REFUSED/FAILED: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
