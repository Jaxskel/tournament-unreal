#!/usr/bin/env python3
"""Check a bounded native weapon report. Emits evidence only, never an Apply plan.

Run against the original project view with -Mode=WeaponReport
-WeaponReportSpec=<report.weapons.json>, or alongside BlobReportSpec in FidelityReport.
Loading may dirty packages in memory: report that fact, never clear it or save it.
Original package bytes must be preserved independently before any later repair.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from material_preflight import ROOTS, finite, object_path, pin_valid, require

ROOT = Path(__file__).resolve().parent
PREFIX = 'COMPAT_WEAPON_REPORT '
SCHEMA = 'ut4-weapon-report-v1'
MASTER = '/Game/RestrictedAssets/Weapons/Global/Material/M_WeaponsBase'


def read_log(text):
    rows, done = [], False
    for line in text.splitlines():
        if PREFIX not in line:
            continue
        require(not done, 'records after completion')
        payload = line.split(PREFIX, 1)[1]
        require(len(payload) <= 8 * 1024 * 1024, 'row budget exceeded')
        row = json.loads(payload)
        require(isinstance(row, dict) and row.get('schema') == SCHEMA, 'unknown report schema')
        finite(row)
        if row.get('kind') == 'complete':
            require(row.get('read_only') is True and row.get('apply_ready') is False,
                    'completion is not read-only')
            require(row.get('materials') == 19 and row.get('meshes') == 4 and
                    sum(r['kind'] == 'material' for r in rows) == 19 and
                    sum(r['kind'] == 'mesh' for r in rows) == 4, 'incomplete report counts')
            done = True
        else:
            require(row.get('kind') in ('material', 'mesh'), 'unknown record kind')
            rows.append(row)
            require(len(rows) <= 23, 'record budget exceeded')
    require(done, 'missing completion: no usable complete report')
    return rows


def skin_evidence(meshes):
    """Evaluate pinned all-LOD resource predicates; these are NOT native method calls.

    SkeletalMesh.cpp2352-2385 uses sections, not the vertex-buffer extra flag.
    Disabled sections also count. No scene/component CPU-skin observation is inferred.
    """
    result, total_lods, total_sections = {}, 0, 0
    for mesh in meshes:
        skin = mesh.get('skin', {})
        require(skin.get('resource') == 'GetResourceForRendering: existing ImportedResource' and
                skin.get('is_editor') is True and skin.get('runtime_component_observed') is False,
                'missing skin resource/view provenance')
        require(skin.get('es2_bone_limit') == 75 and skin.get('sm5_bone_limit') == 256,
                'unexpected pinned feature-level bone limits')
        lods = skin.get('lods', [])
        total_lods += len(lods)
        require(lods and total_lods <= 16 and [x.get('lod') for x in lods] == list(range(len(lods))),
                'missing/all-LOD budget or order failure')
        max_bones, extra, vb_extra = 0, False, False
        for lod in lods:
            for key in ('num_vertices', 'num_tex_coords', 'vertex_buffer_vertices', 'vertex_buffer_tex_coords'):
                require(type(lod.get(key)) is int and lod[key] >= 0, 'invalid LOD count')
            require(type(lod.get('vertex_buffer_extra_influences')) is bool, 'missing vertex buffer influence flag')
            vb_extra |= lod['vertex_buffer_extra_influences']
            sections = lod.get('sections')
            require(isinstance(sections, list), 'missing section rows')
            total_sections += len(sections)
            require(total_sections <= 256 and [x.get('section') for x in sections] == list(range(len(sections))),
                    'section budget or order failure')
            for section in sections:
                for key in ('bone_map_count', 'max_bone_influences', 'num_vertices', 'num_triangles'):
                    require(type(section.get(key)) is int and section[key] >= 0, 'invalid section count')
                require(type(section.get('disabled')) is bool and
                        type(section.get('extra_influences')) is bool and
                        section['extra_influences'] == (section['max_bone_influences'] > 4),
                        'inconsistent section influence flag')
                max_bones = max(max_bones, section['bone_map_count'])
                extra |= section['extra_influences']
        result[mesh['mesh']] = dict(
            evaluation='derived from pinned SkeletalMesh.cpp all-LOD predicates; no native method invocation or live component proof',
            max_bones_per_section=max_bones, extra_influences=extra,
            vertex_buffer_extra_influences=vb_extra, max_palette_over_75=max_bones > 75,
            requires_cpu_skinning_es2=max_bones > skin['es2_bone_limit'] or extra,
            requires_cpu_skinning_sm5=max_bones > skin['sm5_bone_limit'], lods=len(lods))
    return result


def validate(rows):
    spec = json.loads((ROOT / 'report.weapons.json').read_text())
    materials = [r for r in rows if r['kind'] == 'material']
    meshes = [r for r in rows if r['kind'] == 'mesh']
    expected = {object_path(p) for p in spec['targets']}
    require(len(materials) == len(expected) == 19 and {r.get('material') for r in materials} == expected,
            'wrong or duplicate material scope')
    require(len(meshes) == 4 and {r.get('mesh') for r in meshes} == {object_path(p) for p in spec['meshes']},
            'wrong or duplicate mesh scope')
    hashes, dirty, unexpected_bases = {}, [], []
    for row in rows:
        finite(row)
        package = row.get('material', row.get('mesh')).split('.', 1)[0]
        h = row.get('package_sha1', {})
        require(package in h, 'missing own package hash')
        for p, digest in h.items():
            require(isinstance(digest, str) and re.fullmatch(r'[0-9a-fA-F]{40}', digest), 'invalid package hash')
            require(p not in hashes or hashes[p] == digest.lower(), 'inconsistent package provenance')
            hashes[p] = digest.lower()
        require(type(row.get('package_dirty_after_load')) is bool, 'missing dirty observation')
        if row['package_dirty_after_load']:
            dirty.append(package)
    master = next(m for m in materials if m['material'] == object_path(MASTER))
    nodes = master.get('nodes', [])
    paths = {n['path'] for n in nodes}
    require(0 < len(nodes) <= 8192 and len(paths) == len(nodes), 'missing or duplicate graph nodes')
    require(set(master.get('roots', {})) == ROOTS | {'Metallic', 'Roughness', 'Specular'}, 'missing master property pins')
    for label, pin in master['roots'].items():
        pin_valid(pin, label, paths)
    functions = set()
    for n in nodes:
        require(isinstance(n.get('properties'), dict) and all(isinstance(v, str) for v in n['properties'].values()),
                'missing native expression properties')
        require(isinstance(n.get('inputs'), list), 'missing native inputs')
        for pin in n['inputs']:
            pin_valid(pin, n['path'], paths)
        if 'function' in n:
            f = n['function']
            require(isinstance(f, str) and f.startswith(('/Game/', '/Engine/')) and f.split('.', 1)[0] in hashes,
                    'missing function provenance')
            require(any(child.get('owner') == f for child in nodes), 'missing function expressions')
            functions.add(f)
    for m in materials:
        is_master = m is master
        require(m.get('class') == ('Material' if is_master else 'MaterialInstanceConstant'), 'wrong native class')
        chain = m.get('parent_chain', [])
        require(0 < len(chain) <= 32 and len(chain) == len(set(chain)) and chain[0] == m['material'], 'bad parent chain')
        require(chain[-1] == m.get('base_material'), 'base/parent chain mismatch')
        require(all(p.split('.', 1)[0] in hashes for p in chain), 'unhashed parent')
        if m['base_material'] != object_path(MASTER):
            unexpected_bases.append(m['material'])
        require(isinstance(m.get('properties'), dict), 'missing original property bag')
        require(type(m.get('package_dirty_before_description')) is bool, 'missing before-description observation')
        if not is_master:
            require(not m.get('nodes') and not m.get('roots'), 'instance graph unexpectedly duplicated')
            for name in ('ScalarParameterValues', 'VectorParameterValues', 'TextureParameterValues', 'BasePropertyOverrides'):
                require(isinstance(m['properties'].get(name), str), 'missing original override bag: ' + name)
            for name in ('static_overrides', 'static_effective'):
                require(isinstance(m.get(name), dict) and all(isinstance(m[name].get(k), list) for k in ('switches', 'masks', 'terrain')),
                        'missing static parameter evidence')
        for key in ('scalar_parameters', 'vector_parameters', 'texture_parameters'):
            require(isinstance(m.get(key), list), 'missing effective parameter evidence')
            names = [p.get('name') for p in m[key]]
            require(all(isinstance(n, str) for n in names) and len(names) == len(set(names)), 'duplicate/invalid parameter')
            for p in m[key]:
                v = p.get('value')
                require((key == 'scalar_parameters' and type(v) in (float, int)) or
                        (key == 'vector_parameters' and isinstance(v, list) and len(v) == 4 and all(type(c) in (float, int) for c in v)) or
                        (key == 'texture_parameters' and isinstance(v, str)), 'invalid parameter value')
    slots = {}
    for mesh in meshes:
        values = mesh.get('slots', [])
        require(0 < len(values) <= 16 and [s.get('slot') for s in values] == list(range(len(values))), 'bad mesh slots')
        require(all(isinstance(s.get('slot_name'), str) and s.get('material', '').startswith('/Game/') and
                    s['material'].split('.', 1)[0] in hashes for s in values), 'missing slot identity/provenance')
        slots[mesh['mesh']] = [s['material'] for s in values]
    return {'schema': 'ut4-weapon-evidence-v1', 'apply_ready': False,
            'materials': 19, 'meshes': 4, 'master_nodes': len(nodes), 'functions': sorted(functions),
            'dirty_packages': sorted(set(dirty)), 'unexpected_base_materials': sorted(unexpected_bases),
            'mesh_slots': slots, 'skin': skin_evidence(meshes), 'package_sha1': hashes,
            'next_step': 'Review original native function/static branches and provenance before selecting a cloned-master repair.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    data = args.log.read_bytes()
    encoding = 'utf-16' if data.startswith((b'\xff\xfe', b'\xfe\xff')) else 'utf-8-sig'
    result = validate(read_log(data.decode(encoding)))
    result['report_sha256'] = hashlib.sha256(data).hexdigest()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
