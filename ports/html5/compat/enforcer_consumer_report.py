"""Validate the fixed native consumer observation, never authorize an asset edit."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = '/Game/RestrictedAssets/Weapons/Enforcer/'
PACKAGES = [ROOT + suffix for suffix in (
    'Enforcer', 'Enforcer_Attach', 'Dual_Enforcer_Attach',
    'Meshes/Enforcer_1p', 'Meshes/Enforcer_3p', 'Materials/M_Enforcer_Gun',
    'Materials/Materials_thirdPerson/M_Enforcer_Gun_3rdPerson_Inst')]
PREFIX = 'COMPAT_WEAPON_ENFORCER '


def validate(log, inputs):
    raw = inputs.read_bytes()
    if not 0 < len(raw) <= 65536:
        raise ValueError('Input manifest budget')
    spec = json.loads(raw)
    pins = spec.get('packages', [])
    if spec.get('schema') != 'ut4-enforcer-consumer-inputs-v1' or [r.get('package') for r in pins] != PACKAGES:
        raise ValueError('Exact input cohort required')
    run = hashlib.sha1(raw).hexdigest()
    data = log.read_bytes()
    if len(data) > 32 * 1024 * 1024:
        raise ValueError('Log budget')
    text = data.decode('utf-16' if data[:2] in (b'\xff\xfe', b'\xfe\xff') else 'utf-8-sig')
    rows = []
    for line in text.splitlines():
        if PREFIX not in line:
            continue
        value = line.split(PREFIX, 1)[1]
        if len(value) > 65536 or len(rows) >= 8192:
            raise ValueError('Row budget')
        row = json.loads(value)
        if (row.get('schema') != 'ut4-enforcer-consumer-v1' or row.get('run') != run
                or row.get('sequence') != len(rows) or row.get('read_only') is not True
                or row.get('global_usage_complete') is not False
                or row.get('exclusive_runtime_consumption_proven') is not False):
            raise ValueError('Row identity or scope')
        rows.append(row)
    if not rows or rows[0].get('kind') != 'begin' or rows[-1].get('kind') != 'complete':
        raise ValueError('Incomplete observation')
    if sum(r.get('kind') == 'complete' for r in rows) != 1 or any(r.get('kind') in ('error', 'boundary_failure') for r in rows):
        raise ValueError('Failed or repeated observation')
    roots = [r for r in rows if r.get('kind') == 'root']
    if len(roots) != 7 or [r.get('file_pin') for r in roots] != pins:
        raise ValueError('Root pins differ')
    for index, r in enumerate(roots):
        p = PACKAGES[index]
        cls = 'Blueprint' if index < 3 else 'SkeletalMesh' if index < 5 else 'MaterialInstanceConstant'
        if r.get('object') != p + '.' + p.rsplit('/', 1)[-1] or r.get('class') != '/Script/Engine.' + cls:
            raise ValueError('Unexpected root identity')
    done = rows[-1]
    classes = {r.get('class'): r for r in rows if r.get('kind') == 'class' and r.get('class') == r.get('root_class')}
    expected_classes = [p + '.' + p.rsplit('/', 1)[-1] + '_C' for p in PACKAGES[:3]]
    if any(c not in classes or not classes[c].get('cdo') for c in expected_classes):
        raise ValueError('Missing selected class observations')
    if {r.get('cdo') for r in rows if r.get('kind') == 'dual_defaults'} != {classes[c]['cdo'] for c in expected_classes}:
        raise ValueError('Dual defaults do not cover selected classes')
    components = [r for r in rows if r.get('kind') == 'component']
    if len(components) != done.get('components') or not any(r.get('mesh_component') is True for r in components):
        raise ValueError('Component observations do not match completion')
    for p in PACKAGES[3:5]:
        obj = p + '.' + p.rsplit('/', 1)[-1]
        meshes = [r for r in rows if r.get('kind') == 'mesh' and r.get('mesh') == obj]
        if len(meshes) != 1 or type(meshes[0].get('slot_count')) is not int or not 0 < meshes[0]['slot_count'] <= 256:
            raise ValueError('Missing selected mesh slots')
        slots = [r for r in rows if r.get('kind') == 'material_chain' and r.get('context') == obj + ':asset_slot']
        if sorted(r.get('slot', -1) for r in slots) != list(range(meshes[0]['slot_count'])):
            raise ValueError('Incomplete selected mesh material observations')
    if (done.get('root_packages') != 7 or done.get('blueprints') != 3 or done.get('components', 0) <= 0
            or done.get('assets_saved') != 0 or done.get('selected_bytes_unchanged') is not True
            or done.get('runtime_behavior_verified') is not False or done.get('repair_authority') is not False
            or len([r for r in rows if r.get('kind') == 'dual_defaults']) != 3):
        raise ValueError('Completion contract')
    return {'schema': 'ut4-enforcer-consumer-evidence-v1', 'inputs_sha1': run,
            'log_sha256': hashlib.sha256(data).hexdigest(), 'rows': rows,
            'observation_complete': True, 'repair_authority': False,
            'runtime_behavior_verified': False, 'global_usage_complete': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    parser.add_argument('inputs', type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.log, args.inputs), indent=2))
