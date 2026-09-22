#!/usr/bin/env python3
"""Validate the fixed weapon repair and a separately prepared physical COW view.

This tool never copies/restores assets, changes a graph, launches an editor, or cooks.
Default output is a read-only plan. Explicit --project/--original-project inspect a
prepared view; --baseline-out/--receipt-out exclusively create evidence files.
The operator owns backing up old fallbacks and restoring the 18 original MICs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import prepare_cow as cow
import weapon_preflight as report

HERE = Path(__file__).resolve().parent
RECIPE = HERE / 'repair.weapons.json'
RECIPE_SHA1 = '11115c4f91274c90437aac5a1f783a16f3b14279'


def encoded(value):
    return (json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode('utf-8')


def load_recipe(path=RECIPE):
    data = path.read_bytes()
    if hashlib.sha1(data).hexdigest() != RECIPE_SHA1:
        raise ValueError('Recipe differs from reviewed exact scope')
    return json.loads(data)


def baseline(log, recipe):
    raw = Path(log).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != recipe['report_sha256']:
        raise ValueError('Native report differs from reviewed provenance')
    rows = report.read_log(raw.decode('utf-16' if raw[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig'))
    evidence = report.validate(rows)
    materials = [r for r in rows if r['kind'] == 'material']
    for path, sha in recipe['original_sha1'].items():
        if evidence['package_sha1'].get(path) != sha:
            raise ValueError('Source pin mismatch: ' + path)
    if evidence['unexpected_base_materials']:
        raise ValueError('Unexpected original master')
    value = dict(schema='ut4-weapon-fidelity-baseline-v1', report_sha256=digest, materials=materials)
    data = encoded(value)
    if hashlib.sha1(data).hexdigest() != recipe['baseline_sha1']:
        raise ValueError('Baseline serialization differs from native guard')
    return data


def plan(recipe):
    instances = recipe['instances']
    clones = recipe['clones']
    direct = recipe['direct_parents']
    selected = set(instances) | set(clones)
    destinations = set(instances) | set(clones.values())
    saves = set(direct) | set(clones.values())
    if (len(instances), len(clones), len(direct), len(selected), len(destinations), len(saves)) != (18, 5, 4, 23, 23, 9):
        raise ValueError('Invalid fixed operation counts')
    if set(recipe['original_sha1']) != selected or not set(direct) <= set(instances):
        raise ValueError('Invalid source or parent scope')
    if any(not p.startswith('/Game/HTML5Compat/Weapons/V1/') for p in clones.values()):
        raise ValueError('Invalid clone namespace')
    if any(not cow.PACKAGE.fullmatch(p) for p in selected | destinations):
        raise ValueError('Invalid package syntax')
    return dict(schema='ut4-weapon-fidelity-plan-v1', recipe_sha1=RECIPE_SHA1,
                report_sha256=recipe['report_sha256'], baseline_sha1=recipe['baseline_sha1'],
                source_sha1=recipe['original_sha1'], physical_destinations=sorted(destinations),
                restore_original_mics=list(instances), must_be_absent=sorted(clones.values()),
                native_save_allowlist=sorted(saves), byte_identical_mics=sorted(set(instances)-set(direct)),
                native_modes=['WeaponRepairApply', 'WeaponRepairVerify'],
                asset_writes_performed=False, shader_runtime_validated=False)


def preflight(project, original_project, recipe):
    """Inspect only physical destinations; source views may not redirect selected files."""
    operation = plan(recipe)
    project = cow.physical(project)
    original = cow.physical(original_project)
    if cow.inside(project, original) or cow.inside(original, project):
        raise ValueError('Original and private projects must be disjoint')
    content = cow.physical(project / 'Content')
    source = cow.physical(original / 'Content')
    cow.physical(project / 'UnrealTournament.uproject')
    cow.physical(original / 'UnrealTournament.uproject')
    # No destructive recovery: any mismatch leaves the operator's assets untouched.
    for p, expected in recipe['original_sha1'].items():
        f = cow.physical(source / cow.relative_asset(p))
        if not f.is_file() or cow.sha1(f) != expected:
            raise ValueError('Original source bytes differ: ' + p)
    for p in recipe['instances']:
        f = cow.physical(content / cow.relative_asset(p))
        if not f.is_file() or cow.sha1(f) != recipe['original_sha1'][p]:
            raise ValueError('MIC not restored byte-exactly: ' + p)
    for p in recipe['clones'].values():
        f = content / cow.relative_asset(p)
        cow.physical(f.parent)
        cow.physical(f, allow_missing=True)
        if os.path.lexists(f):
            raise ValueError('Clone destination already exists: ' + p)
    return dict(schema=1, operation='fixed-weapon-fidelity-repair', manifest_sha1=RECIPE_SHA1,
                project_dir=str(project), content_root=str(content), original_root=str(original),
                source_sha1=recipe['original_sha1'],
                files=[dict(package=p, file=str(content / cow.relative_asset(p)))
                       for p in operation['physical_destinations']],
                native_save_allowlist=operation['native_save_allowlist'],
                byte_identical_mics=operation['byte_identical_mics'], shader_runtime_validated=False)


def write_new(path, data, forbidden=()):
    path = cow.physical(path, allow_missing=True)
    if any(cow.inside(path, root) for root in forbidden):
        raise ValueError('Evidence output must be outside asset Content roots')
    cow.physical(path.parent)
    with path.open('xb') as stream:
        stream.write(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--project', type=Path)
    parser.add_argument('--original-project', type=Path)
    parser.add_argument('--baseline-out', type=Path)
    parser.add_argument('--receipt-out', type=Path)
    args = parser.parse_args()
    try:
        recipe = load_recipe()
        data = baseline(args.log, recipe)
        if bool(args.project) != bool(args.original_project):
            raise ValueError('Both project paths are required for COW inspection')
        receipt = preflight(args.project, args.original_project, recipe) if args.project else None
        if args.receipt_out and receipt is None:
            raise ValueError('Receipt requires successful physical COW preflight')
        forbidden = tuple(Path(receipt[k]) / ('Content' if k == 'original_root' else '')
                          for k in ('original_root', 'content_root')) if receipt else ()
        if args.baseline_out:
            write_new(args.baseline_out, data, forbidden)
        if args.receipt_out:
            write_new(args.receipt_out, encoded(receipt), forbidden)
        print(json.dumps(dict(plan=plan(recipe), cow_preflight=receipt), indent=2))
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
