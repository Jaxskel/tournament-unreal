"""Local Python-only contract tests and strict native-log validation.

No engine/compiler invocation. --private-source verifies private captured files;
--native-log additionally requires a completed native report. Passing unit tests
alone is never native execution, shader coverage, or material-change approval.
"""
import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
import ntpath
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import sys
import unittest

HERE = Path(__file__).resolve().parent
HEADER = HERE / 'UT4Html5Compat/Source/UT4Html5Compat/Private/WeaponUsageReport.h'
SPEC = HERE / 'report.weapon-usage.json'
SCHEMA = 'ut4-weapon-usage-v2'
PREFIX = 'COMPAT_WEAPON_USAGE '
DIAGNOSTIC_PREFIX = 'COMPAT_WEAPON_USAGE_DIAGNOSTIC '
DIAGNOSTIC_SCHEMA = 'ut4-weapon-usage-diagnostic-v1'
FAILURE_KINDS = {'load_observation', 'registry_query_failure', 'inventory_failure'}
KINDS = set('begin input read_root scope_seed package_dependency config_assignment initial_package registry_asset package_file registry mic referencer blueprint derived_class defaults component component_scan mesh map streaming map_scope lighting lighting_component actor class scs inherited add_component_template file complete'.split()) | FAILURE_KINDS
DIAGNOSTIC_KINDS = set('begin input read_root scope_seed package_dependency config_assignment initial_package registry_asset package_file registry mic file referencer_metadata historical_failure diagnostic_end'.split()) | FAILURE_KINDS
SHA1 = re.compile(r'[0-9a-f]{40}\Z')
PRIVATE = None
NATIVE_LOG = None
NATIVE_EXIT_CODE = None


def resident_bytes(path):
    # macOS can evict previously verified captures. Fail immediately instead of
    # implicitly waiting for cloud hydration during a local-only test.
    flags = getattr(path.stat(), 'st_flags', 0)
    require(not flags & getattr(stat, 'SF_DATALESS', 0x40000000), 'capture is dataless; local bytes unavailable: ' + str(path))
    return path.read_bytes()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load_records(path, prefix=PREFIX):
    """Stream bounded log records; do not mistake a partial log for completion."""
    records = []
    chars = 0
    with Path(path).open(encoding='utf-8-sig', errors='strict') as stream:
        for line in stream:
            other = DIAGNOSTIC_PREFIX if prefix == PREFIX else PREFIX
            require(other not in line, 'mixed or wrong usage prefix')
            if prefix not in line:
                continue
            payload = line.split(prefix, 1)[1].rstrip('\r\n')
            chars += len(payload)
            require(len(payload) <= 65536 and chars <= 536870912 and len(records) < 2000000, 'log budget')
            records.append(json.loads(payload))
    return records


def unique(rows, key):
    result = {}
    for row in rows:
        k = key(row)
        require(k not in result, 'duplicate identity: ' + str(k))
        result[k] = row
    return result


def local_path(path):
    require(isinstance(path, str) and re.fullmatch(r'[A-Za-z]:/[^:]+', path) is not None, 'local drive path required')
    require(ntpath.normpath(path).replace('\\', '/') == path and not path.endswith('/'), 'canonical path required')
    return path


def read_roots(rows):
    require(0 < len(rows) <= 1024, 'read root budget')
    roots = unique(rows, lambda r: local_path(r['logical_root']).casefold())
    for r in roots.values():
        local_path(r['physical_root'])
        require(r['role'] in {'source', 'selected'}, 'read root role')
    return roots


def mapped_target(path, roots):
    local_path(path)
    matches = [r for p, r in roots.items() if path.casefold() == p or path.casefold().startswith(p + '/')]
    require(matches, 'unapproved read path')
    root = max(matches, key=lambda r: len(r['logical_root']))
    return root, root['physical_root'] + path[len(root['logical_root']):]


def validate(records, *, diagnostic=False):
    spec = json.loads(SPEC.read_text())
    require(len(records) >= 2, 'empty/partial report')
    require(len(records) <= spec['limits']['rows'], 'row budget')
    terminal = 'diagnostic_end' if diagnostic else 'complete'
    require(records[0]['kind'] == 'begin' and records[-1]['kind'] == terminal, 'missing terminal completion')
    by = defaultdict(list)
    run = records[0]['run']
    require(SHA1.fullmatch(run) is not None, 'invalid input-manifest binding')
    for seq, row in enumerate(records):
        require(row.get('kind') in (DIAGNOSTIC_KINDS if diagnostic else KINDS), 'unknown record kind')
        require(row['kind'] not in FAILURE_KINDS, 'failure observation cannot be completed')
        require(row.get('sequence') == seq and row.get('schema') == (DIAGNOSTIC_SCHEMA if diagnostic else SCHEMA) and row.get('run') == run, 'sequence/schema/run mismatch')
        require(row.get('complete') is (not diagnostic and seq == len(records) - 1), 'partial record claims completion')
        if diagnostic:
            require(row.get('cohort') == 'materials' and row.get('global_usage_complete') is False
                    and row.get('global_scope_status') == 'global_not_revalidated', 'diagnostic scope/global claim')
        require(row.get('read_only') is True and row.get('authorizes_material_flag_change') is False, 'unsafe report claim')
        by[row['kind']].append(row)
    require(len(by['begin']) == len(by[terminal]) == len(by['registry']) == 1, 'duplicate/missing report boundary')
    begin, done, registry = records[0], records[-1], by['registry'][0]
    require(begin['spec_sha1'] == hashlib.sha1(SPEC.read_bytes()).hexdigest(), 'spec binding')
    require(begin['proof_sha1'] == spec['proof_sha1'] and begin['master'] == spec['master'], 'generation binding')
    require(begin['cook_maps'] == spec['cook_maps'], 'cook root drift')
    counts = Counter(row['kind'] for row in records[:-1])
    counts_key, rows_key = ('row_counts_before_end', 'rows_before_end') if diagnostic else ('row_counts_before_complete', 'rows_before_complete')
    require(done[counts_key] == dict(counts) and done[rows_key] == len(records) - 1, 'incomplete row counts')
    for field, kind in [('files', 'file'), ('classes', 'class'), ('maps', 'map'), ('actors', 'actor'), ('components', 'component_scan'), ('mic_count', 'mic')]:
        require(done[field] == len(by[kind]), 'incomplete ' + kind)
    for field in ['files', 'classes', 'maps', 'actors', 'components']:
        require(done[field] <= spec['limits'][field], 'report budget: ' + field)
    require(done['input_bytes'] <= spec['limits']['bytes'], 'input byte budget')
    require(done['all_fingerprints_unchanged'] is True and done['new_dirty_packages'] is False and done['assets_saved'] == 0, 'read-only invariant')
    require(done['runtime_blueprint_behavior_verified'] is False and done['effective_html5_cvars_verified'] is False, 'unsupported runtime assertion')
    require(SHA1.fullmatch(done['master_sha1']) is not None, 'master hash')
    require(registry['search_all_assets_synchronous'] is True and registry['is_loading_assets'] is False and registry['on_disk_assets_only'] is True, 'registry provenance')
    require(registry['assets'] == len(by['registry_asset']) > 0, 'registry count')
    unique(by['registry_asset'], lambda r: r['object'])
    packages = unique(by['package_file'], lambda r: r['package'])
    require(registry['packages'] == len(packages), 'package inventory')
    files = unique(by['file'], lambda r: r['path'].casefold())
    roots = read_roots(by['read_root'])
    expected_scope = 'materials-prerequisites-preloaded-forward-closure' if diagnostic else 'relevant-reference-class-map-dependencies-and-preloaded'
    require(registry['fingerprint_scope'] == expected_scope, 'fingerprint scope')
    require(len(packages) <= spec['limits']['packages'], 'package budget')
    require(len(files) > 0 and sum(r['bytes'] for r in files.values()) == done['input_bytes'], 'file byte accounting')
    for f in files.values():
        require(f['target_before'] == f['target_after'], 'logical target drift')
        if f['read_only_mapping']:
            root, expected = mapped_target(f['path'], roots)
            require(f['target_before'].casefold() == expected.casefold(), 'unapproved physical target')
            require(f['logical_root'] == root['logical_root'] and f['physical_root'] == root['physical_root'], 'root provenance mismatch')
        else:
            require(f['target_before'] == f['path'] and f['logical_root'] == f['physical_root'] == '', 'strict path was resolved')
        require(isinstance(f['bytes'], int) and f['bytes'] >= 0, 'invalid file size')
        require(f['bytes'] <= spec['limits']['file_bytes'], 'file byte budget')
        require(f['sha1_before'] == f['sha1_after'] and f['physical_before'] == f['physical_after'], 'file/physical drift')
        if f['missing']:
            require(f['bytes'] == 0 and f['sha1_before'] == f['physical_before'] == '', 'false absence')
        else:
            require(SHA1.fullmatch(f['sha1_before']) is not None and f['physical_before'], 'missing fingerprint')
    for p in packages.values():
        require(p['file'].casefold() in files and not files[p['file'].casefold()]['missing'], 'unpinned package')
    # The global registry is metadata-only. Scope seeds and existing dependencies,
    # not every unrelated registry asset, must have complete file fingerprints.
    seeds = unique(by['scope_seed'], lambda r: r['package'])
    required_seeds = set(spec['materials_diagnostic']['prerequisite_packages']) if diagnostic else {spec['master'], *spec['cook_maps']}
    require(required_seeds <= seeds.keys() <= packages.keys(), 'required scope seeds')
    dependencies = unique(by['package_dependency'], lambda r: (r['from'], r['package']))
    require(len(dependencies) <= spec['limits']['edges'], 'dependency edge budget')
    for row in dependencies.values():
        require(row['from'] in packages, 'dependency outside scope')
        if row['exists']:
            require(row['package'] in packages, 'unpinned dependency')
        else:
            require(row['hard'] is False and row['package'] not in packages, 'missing required dependency')
    roles = {r['role'] for r in by['input']}
    require(set(spec['input_manifest_required_roles']) <= roles, 'input provenance roles')
    unique(by['input'], lambda r: r['path'].casefold())
    for row in by['input']:
        f = files.get(row['path'].casefold())
        require(f and f['sha1_before'] == row['sha1'], 'input hash mismatch')

    master = spec['master']
    mics = unique(by['mic'], lambda r: r['package'])
    selected = set(json.loads((HERE / 'repair.weapons.json').read_text())['instances'])
    require(len(mics) == 20 and selected <= mics.keys(), 'incomplete MIC closure')
    def object_path(package):
        return package + '.' + package.rsplit('/', 1)[1]
    parents = {}
    for p, row in mics.items():
        require(p in packages and row['material'] == object_path(p), 'MIC identity')
        parents[p] = row['parent'].split('.', 1)[0]
    for p in mics:
        seen = set()
        while p != master:
            require(p in parents and p not in seen, 'MIC parent cycle/disconnected closure')
            seen.add(p)
            p = parents[p]
    closure_objects = {object_path(p) for p in set(mics) | {master}}
    unique(by['referencer'], lambda r: (r['dependency'], r['referencer']))
    for row in by['referencer']:
        require(row['dependency'] in packages and row['referencer'] in packages, 'unclassified referencer package')

    if diagnostic:
        require(done['cohort_status'] == 'observed' and done['fresh_verify_passed'] is True, 'cohort not verified')
        require(mics.keys() <= seeds.keys(), 'MIC not a preflight seed')
        require(len(by['historical_failure']) == 1, 'missing historical failure')
        history = by['historical_failure'][0]
        for key, expected in spec['materials_diagnostic']['historical_failure'].items():
            require(history.get(key) == expected, 'historical failure altered: ' + key)
        for pin in spec['materials_diagnostic']['history_files']:
            inputs = [r for r in by['input'] if r['role'] == pin['role']]
            require(len(inputs) == 1 and inputs[0]['sha1'] == pin['sha1'], 'history input role/hash')
            f = files.get(inputs[0]['path'].casefold())
            require(f and not f['missing'] and not f['read_only_mapping'] and f['bytes'] == pin['bytes'], 'history strict pin')
            field = 'report_path' if pin['role'].endswith('-log') else 'result_path'
            require(history[field] == inputs[0]['path'], 'history provenance path')
        unique(by['referencer_metadata'], lambda r: (r['dependency'], r['referencer']))
        for row in by['referencer_metadata']:
            require(row['edge_types'] == 'Packages' and row['native_coverage_claimed'] is False, 'external native coverage claim')
        return {'status': 'valid_cohort_diagnostic', 'cohort': 'materials', 'complete': False,
                'global_usage_complete': False, 'authorizes_material_flag_change': False, 'mics': len(mics), 'files': len(files)}

    maps = unique(by['map'], lambda r: r['package'])
    require(set(spec['cook_maps']) <= maps.keys(), 'missing cook root')
    scopes = unique(by['map_scope'], lambda r: r['root'])
    require(set(spec['cook_maps']) <= scopes.keys(), 'missing cook scope')
    for p, row in maps.items():
        require(p in packages and row['world_initialized_by_report'] is False, 'unsafe/unpinned map')
        require(set(row['sublevels_and_lods']) <= maps.keys(), 'missing sublevel')
    for root, row in scopes.items():
        reached, queue = set(), [root]
        while queue:
            p = queue.pop()
            require(p in maps, 'unknown scope map')
            if p in reached:
                continue
            reached.add(p)
            queue.extend(maps[p]['sublevels_and_lods'])
        require(len(row['maps']) == len(set(row['maps'])) and set(row['maps']) == reached, 'truncated map reachability')
    require(set().union(*(set(r['maps']) for r in scopes.values())) == maps.keys(), 'uncovered map')

    classes = unique(by['class'], lambda r: r['class'])
    require(set(spec['native_bases']) <= classes.keys(), 'missing native family')
    defaults = unique(by['defaults'], lambda r: (r['object'], r['context']))
    for c in classes.values():
        require((c['cdo'], 'cdo') in defaults, 'missing native CDO defaults')
    for d in defaults.values():
        require(d['pickup_function_executed'] is False, 'Blueprint execution forbidden')
        require(d['pickup_script_override'] is (d['pickup_script_bytes'] > 0), 'Script override identity')
    for row in by['blueprint']:
        require(row['class'] in classes, 'missing Blueprint class')
    unique(by['derived_class'], lambda r: r['name'])
    class_names = {c.rsplit('.', 1)[-1] for c in classes}
    for row in by['derived_class']:
        require(row['name'] in class_names, 'uncovered registry-derived class')
    actors = unique(by['actor'], lambda r: r['actor'])
    scans = unique(by['component_scan'], lambda r: (r['component'], r['context']))
    meshes = unique(by['component'], lambda r: (r['component'], r['context']))
    assets = unique(by['mesh'], lambda r: r['mesh'])
    for key, scan in scans.items():
        require((key in meshes) is scan['mesh'], 'unreported component slots')
    for key, comp in meshes.items():
        require(key in scans and scans[key]['mesh'], 'unscanned mesh')
        require(not comp['mesh'] or comp['mesh'] in assets, 'missing mesh defaults')
        slots = unique(comp['slots'], lambda r: r['slot'])
        require(len(slots) <= 256 and 0 <= comp['resolved_slot_count'] <= len(slots), 'slot coverage')
        require(set(slots) == set(range(len(slots))), 'truncated slot indices')
        for row in slots.values():
            expected_hit = row['resolved'] in closure_objects or row['resolved_base'] == object_path(master)
            require(row['closure_hit'] is expected_hit, 'material closure classification')
    scan_counts = Counter(ctx for _, ctx in scans)
    level_packages = {r['level']: p for p,r in maps.items()}
    for a in actors.values():
        require(a['components'] == scan_counts[a['actor']], 'actor component coverage')
        require(a['level'] in level_packages, 'actor outside map scope')
        if a['pickup_family']:
            require((a['actor'], 'placed_pickup') in defaults, 'pickup instance override missing')
    for row in by['scs']:
        require((row['actual_template'], row['class'] + ':scs:' + row['node']) in scans, 'missing actual SCS template')
    for row in by['inherited']:
        require((row['template'], row['class'] + ':inherited:' + row['handler']) in scans, 'missing inherited override')
    for row in by['add_component_template']:
        require((row['template'], row['class'] + ':add_component:' + row['owner_class']) in scans, 'missing AddComponent template')
    lighting = unique(by['lighting_component'], lambda r: r['component'])
    lightrows = unique(by['lighting'], lambda r: (r['component'], r['lod'], r['source'], r['source_owner']))
    light_by_lod = defaultdict(list)
    for row in lightrows.values():
        light_by_lod[row['component'], row['lod']].append(row)
    placed_components = {c for c,ctx in scans if ctx in actors}
    for (comp, ctx), row in meshes.items():
        if ctx in actors and row['is_static_mesh']:
            require(comp in lighting, 'placed static mesh lacks lighting inspection')
    for comp, row in lighting.items():
        require(row['native_active_lookup_executed'] is False and 0 <= row['lods'] <= 64, 'unsafe LCI assertion')
        require(comp in placed_components, 'lightmap on unscanned component')
        for lod in range(row['lods']):
            lod_rows = light_by_lod[comp, lod]
            sources = [r['source'] for r in lod_rows]
            for source in ['override', 'legacy_lod', 'legacy_annotation', 'own_level_registry']:
                require(sources.count(source) == 1, 'missing serialized lighting source')
            map_package = level_packages.get(row['level'])
            require(map_package is not None, 'lighting level not covered')
            candidates = {m['level'] for p,m in maps.items() if m.get('lighting_scenario') and p != map_package
                          and any(p in scope['maps'] and map_package in scope['maps'] for scope in scopes.values())}
            actual = {r['source_owner'] for r in lod_rows if r['source'] == 'scenario_registry_candidate'}
            require(actual == candidates, 'lighting scenario coverage')
    for row in lightrows.values():
        require(row['component'] in lighting and 0 <= row['lod'] < lighting[row['component']]['lods'], 'unknown lightmap LOD')
        require(row['active_world_selection_claimed'] is False, 'runtime lightmap selection unsupported')
        require(not row['lightmap_2d'] or row['lightmap_present'], 'invalid 2D lightmap presence')
        require(not row['lightmap_present'] or row['record_present'], 'invalid lightmap record')
    return {'complete': True, 'mics': len(mics), 'maps': len(maps), 'classes': len(classes), 'files': len(files), 'runtime_proof': False}


def fixture():
    """Synthetic structural fixture, deliberately not evidence about UT assets."""
    spec = json.loads(SPEC.read_text())
    master = spec['master']
    selected = json.loads((HERE / 'repair.weapons.json').read_text())['instances']
    micpaths = selected + ['/Fixture/DescendantA', '/Fixture/DescendantB']
    allpackages = [master] + micpaths + spec['cook_maps']
    rows = []
    def add(kind, **data):
        rows.append(dict(kind=kind, **data))
    add('begin', spec_sha1=hashlib.sha1(SPEC.read_bytes()).hexdigest(), proof_sha1=spec['proof_sha1'], master=master, cook_maps=spec['cook_maps'])
    add('read_root', logical_root='C:/Fixture', physical_root='D:/Original', role='source')
    for i, p in enumerate(allpackages):
        file = 'C:/Fixture/' + str(i) + '.uasset'
        add('registry_asset', object=p + '.' + p.rsplit('/', 1)[1], package=p)
        add('package_file', package=p, file=file)
        add('scope_seed', package=p)
        add('file', path=file, target_before='D:/Original/'+str(i)+'.uasset', target_after='D:/Original/'+str(i)+'.uasset',
            read_only_mapping=True, logical_root='C:/Fixture', physical_root='D:/Original',
            missing=False, bytes=1, sha1_before='a'*40, sha1_after='a'*40, physical_before=str(i), physical_after=str(i))
    for i, role in enumerate(spec['input_manifest_required_roles']):
        add('input', path='C:/Fixture/' + str(i) + '.uasset', sha1='a'*40, role=role)
    add('registry', fingerprint_scope='relevant-reference-class-map-dependencies-and-preloaded', search_all_assets_synchronous=True, is_loading_assets=False, on_disk_assets_only=True, assets=len(allpackages), packages=len(allpackages))
    for p in micpaths:
        add('mic', package=p, material=p+'.'+p.rsplit('/', 1)[1], parent=master+'.M_WeaponsBase')
    for p in spec['cook_maps']:
        add('map', package=p, level=p+'.Level', world_initialized_by_report=False, sublevels_and_lods=[])
        add('map_scope', root=p, maps=[p])
    for p in spec['native_bases']:
        add('class', **{'class': p, 'cdo': p+'.Default'})
        add('defaults', object=p+'.Default', context='cdo', pickup_function_executed=False, pickup_script_override=False, pickup_script_bytes=0)
    actor, component = '/Fixture/Actor', '/Fixture/Actor.Mesh'
    add('actor', actor=actor, level=spec['cook_maps'][0]+'.Level', components=1, pickup_family=False)
    add('component_scan', component=component, context=actor, mesh=True)
    add('component', component=component, context=actor, mesh='', is_static_mesh=True, resolved_slot_count=1, slots=[dict(slot=0, resolved=selected[0]+'.'+selected[0].rsplit('/', 1)[1], resolved_base=master+'.M_WeaponsBase', closure_hit=True)])
    add('lighting_component', component=component, level=spec['cook_maps'][0]+'.Level', lods=1, native_active_lookup_executed=False)
    for source in ['override', 'legacy_lod', 'legacy_annotation', 'own_level_registry']:
        add('lighting', component=component, lod=0, source=source, source_owner='', active_world_selection_claimed=False, record_present=False, lightmap_present=False, lightmap_2d=False)
    add('complete', master_sha1='b'*40, all_fingerprints_unchanged=True, new_dirty_packages=False, assets_saved=0, input_bytes=len(allpackages), runtime_blueprint_behavior_verified=False, effective_html5_cvars_verified=False)
    reseal(rows)
    return rows


def reseal(rows):
    for seq, row in enumerate(rows):
        row.update(sequence=seq, schema=SCHEMA, run='c'*40, complete=row['kind']=='complete', read_only=True, authorizes_material_flag_change=False)
    done = rows[-1]
    counts = Counter(r['kind'] for r in rows[:-1])
    done['row_counts_before_complete'] = dict(counts)
    done['rows_before_complete'] = len(rows)-1
    for field, kind in [('files','file'), ('classes','class'), ('maps','map'), ('actors','actor'), ('components','component_scan'), ('mic_count','mic')]:
        done[field] = counts[kind]


def reseal_diagnostic(rows):
    reseal(rows)
    for row in rows:
        row.update(schema=DIAGNOSTIC_SCHEMA, cohort='materials', complete=False,
                   global_usage_complete=False, global_scope_status='global_not_revalidated')
    done = rows[-1]
    done['row_counts_before_end'] = done.pop('row_counts_before_complete')
    done['rows_before_end'] = done.pop('rows_before_complete')


def diagnostic_fixture():
    # Build independent cohort records, with no fake empty class/map records.
    spec = json.loads(SPEC.read_text())
    rows = [r for r in fixture() if r['kind'] in DIAGNOSTIC_KINDS or r['kind'] == 'complete']
    done = rows.pop(); done.update(kind='diagnostic_end', cohort_status='observed', fresh_verify_passed=True)
    known = {r['package'] for r in rows if r['kind'] == 'package_file'}
    for i, package in enumerate(spec['materials_diagnostic']['prerequisite_packages']):
        if package in known:
            continue
        path = 'C:/Fixture/prereq' + str(i) + '.uasset'
        target = path.replace('C:/Fixture', 'D:/Original')
        rows.extend([dict(kind='package_file', package=package, file=path), dict(kind='scope_seed', package=package),
                     dict(kind='file', path=path, target_before=target, target_after=target, read_only_mapping=True,
                          logical_root='C:/Fixture', physical_root='D:/Original', missing=False, bytes=1,
                          sha1_before='a'*40, sha1_after='a'*40, physical_before=path, physical_after=path)])
    history = dict(kind='historical_failure', **spec['materials_diagnostic']['historical_failure'])
    for pin in spec['materials_diagnostic']['history_files']:
        path = 'C:/Evidence/' + pin['role']
        rows.extend([dict(kind='input', path=path, role=pin['role'], sha1=pin['sha1']),
                     dict(kind='file', path=path, target_before=path, target_after=path, read_only_mapping=False,
                          logical_root='', physical_root='', missing=False, bytes=pin['bytes'],
                          sha1_before=pin['sha1'], sha1_after=pin['sha1'], physical_before=path, physical_after=path)])
        history['report_path' if pin['role'].endswith('-log') else 'result_path'] = path
    rows.append(history)
    # External reverse references do not confer admission or native coverage.
    rows.append(dict(kind='referencer_metadata', dependency=spec['master'], referencer='/Unshipped/World',
                     edge_types='Packages', native_coverage_claimed=False))
    registry = next(r for r in rows if r['kind'] == 'registry')
    registry.update(fingerprint_scope='materials-prerequisites-preloaded-forward-closure',
                    packages=sum(r['kind'] == 'package_file' for r in rows))
    done['input_bytes'] = sum(r['bytes'] for r in rows if r['kind'] == 'file')
    rows.append(done); reseal_diagnostic(rows); return rows


class UsageTests(unittest.TestCase):
    def test_spec_is_immutable_and_generation_bound(self):
        text = HEADER.read_text()
        self.assertIn(hashlib.sha1(SPEC.read_bytes()).hexdigest(), text)
        spec = json.loads(SPEC.read_text())
        self.assertEqual(spec['expected_mic_count'], 20)
        self.assertEqual(spec['authorizes_material_flag_change'], False)

    def test_no_forbidden_operations(self):
        text = re.sub(r'//[^\n]*', '', HEADER.read_text())
        for forbidden in [r'\bSavePackage\s*\(', r'\bSetDirtyFlag\s*\(', r'\bMarkPackageDirty\s*\(', r'\bInitWorld\s*\(',
                          r'\bBeginPlay\s*\(', r'\bProcessEvent\s*\(', r'\bNewObject\s*[<(]', r'\bPostEditChange\s*\(',
                          r'\bGetPickupMeshTemplate(?:_Implementation)?\s*\(', r'\bHandleLegacyMapBuildData\s*\(',
                          r'\bGetAndRemoveAnnotation\s*\(', r'bUsedWithStaticLighting\s*=', r'\bAllocateMeshBuildData\s*\(']:
            self.assertNotRegex(text, forbidden)
        self.assertIn('WeaponTessellationUpgrade(Params, true)', text)
        self.assertNotIn('WeaponTessellationUpgrade(Params, false)', text)
        self.assertNotRegex(text, r'GetDefaultObject\(\s*\)')

    def test_native_gate_order_and_completeness(self):
        text = HEADER.read_text().split('static int32 WeaponUsageReport(')[1]
        gates = ['usage-admission', 'R.RegistryRows(true)', 'R.Ledger.Check()', 'WeaponTessellationUpgrade(Params, true)',
                 'R.Materials()', 'R.DiscoverClasses()', 'R.Maps()', 'R.PlacedActors()', 'R.Templates()',
                 'R.RegistryRows(false)', 'R.QueryUnchanged()', 'R.Ledger.Check(&R.Log)', 'R.Log.Emit(TEXT("complete")']
        positions = [text.index(g) for g in gates]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(HEADER.read_text().count('R.Log.Emit(TEXT("complete")'), 1)
        self.assertIn('FILE_SHARE_READ, nullptr, OPEN_EXISTING', HEADER.read_text())
        self.assertNotIn('FILE_SHARE_WRITE', HEADER.read_text())
        self.assertIn('GComponentsWithLegacyLightmaps.GetAnnotationMap().Find(C)', HEADER.read_text())

    def test_structural_fixture_passes_without_runtime_claim(self):
        result = validate(fixture())
        self.assertEqual(result['mics'], 20)
        self.assertFalse(result['runtime_proof'])

    def reject_mutation(self, mutate, reseal_counts=False):
        rows = fixture()
        mutate(rows)
        if reseal_counts:
            reseal(rows)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            validate(rows)

    def test_truncation_at_every_record_rejected(self):
        rows = fixture()
        for count in range(len(rows)):
            with self.subTest(count=count), self.assertRaises(ValueError):
                validate(rows[:count])

    def test_deleted_evidence_rejected_even_with_forged_counts(self):
        for kind in ['mic', 'map_scope', 'map', 'class', 'defaults', 'component_scan', 'component', 'lighting', 'package_file', 'input']:
            with self.subTest(kind=kind):
                self.reject_mutation(lambda rows: rows.pop(next(i for i,r in enumerate(rows) if r['kind']==kind)), True)

    def test_hash_identity_and_readonly_mismatch_rejected(self):
        for field, value in [('sha1_after', 'e'*40), ('physical_after','changed'), ('missing',True), ('bytes',-1)]:
            with self.subTest(field=field):
                self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='file').update({field:value}))
        self.reject_mutation(lambda rows: rows[-1].update(assets_saved=1))
        self.reject_mutation(lambda rows: rows[-1].update(effective_html5_cvars_verified=True))
        self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='defaults').update(pickup_function_executed=True))

    def test_cycles_sublevels_false_hits_and_missing_legacy_rejected(self):
        self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='mic').update(parent='/Outside/Other.Other'))
        self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='map')['sublevels_and_lods'].append('/Missing/Sublevel'))
        self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='component')['slots'][0].update(closure_hit=False))
        self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='lighting').update(source='omitted_legacy'))

    def test_duplicate_and_mixed_run_rejected(self):
        self.reject_mutation(lambda rows: rows.insert(-1, copy.deepcopy(next(r for r in rows if r['kind']=='mic'))), True)
        self.reject_mutation(lambda rows: rows[1].update(run='d'*40))

    def test_static_mesh_cannot_omit_all_lighting_rows(self):
        self.reject_mutation(lambda rows: rows.__setitem__(slice(None), [r for r in rows if r['kind'] not in {'lighting', 'lighting_component'}]), True)

    def test_registry_class_cannot_be_silently_skipped(self):
        self.reject_mutation(lambda rows: rows.insert(-1, {'kind':'derived_class', 'name':'MissingWeapon_C'}), True)

    def test_related_lighting_scenario_cannot_be_silently_skipped(self):
        def mutate(rows):
            maps = [r for r in rows if r['kind']=='map']
            maps[1]['lighting_scenario'] = True
            maps[0]['sublevels_and_lods'].append(maps[1]['package'])
            next(r for r in rows if r['kind']=='map_scope' and r['root']==maps[0]['package'])['maps'].append(maps[1]['package'])
        self.reject_mutation(mutate)

    def test_reviewed_mapping_uses_longest_root_and_component_boundary(self):
        roots = read_roots([
            dict(logical_root='C:/Selected/Content', physical_root='C:/Selected/Content', role='selected'),
            dict(logical_root='C:/Selected/Content/Maps', physical_root='D:/Original/Maps', role='source')])
        self.assertEqual(mapped_target('C:/Selected/Content/Maps/Deck.umap', roots)[1], 'D:/Original/Maps/Deck.umap')
        self.assertEqual(mapped_target('C:/Selected/Content/MapsExtra/X.uasset', roots)[1], 'C:/Selected/Content/MapsExtra/X.uasset')
        for path in ['C:/Selected/ContentX/X.uasset', 'C:/Selected/Content/../Secret', '//server/share/Content/X', 'C:/Selected/Content/X:stream']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                mapped_target(path, roots)
        with self.assertRaises(ValueError):
            read_roots([dict(logical_root='C:/Root', physical_root='D:/A', role='source'),
                        dict(logical_root='c:/root', physical_root='D:/B', role='source')])

    def test_target_redirect_rejected_even_when_bytes_identity_match(self):
        self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='file').update(target_after='D:/Elsewhere/0.uasset'))
        self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='file').update(target_before='D:/Elsewhere/0.uasset', target_after='D:/Elsewhere/0.uasset'))
        self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='file').update(physical_root='D:/Elsewhere'))

    def test_strict_proof_path_cannot_claim_resolved_target(self):
        self.reject_mutation(lambda rows: next(r for r in rows if r['kind']=='file').update(read_only_mapping=False, logical_root='', physical_root=''))
        rows = fixture(); row = next(r for r in rows if r['kind']=='file')
        row.update(read_only_mapping=False, logical_root='', physical_root='', target_before=row['path'], target_after=row['path'])
        self.assertTrue(validate(rows)['complete'])

    def test_absent_sidecar_keeps_mapping_provenance(self):
        rows = fixture(); row = copy.deepcopy(next(r for r in rows if r['kind']=='file'))
        row.update(path='C:/Fixture/0.ubulk', target_before='D:/Original/0.ubulk', target_after='D:/Original/0.ubulk',
                   missing=True, bytes=0, sha1_before='', sha1_after='', physical_before='', physical_after='')
        rows.insert(-1, row); reseal(rows); self.assertTrue(validate(rows)['complete'])
        row['target_after'] = 'D:/Different/0.ubulk'
        with self.assertRaises(ValueError): validate(rows)

    def test_unrelated_registry_assets_need_no_file_fingerprint(self):
        rows = fixture()
        rows.insert(-1, dict(kind='registry_asset', object='/Unrelated/Missing.Missing', package='/Unrelated/Missing'))
        next(r for r in rows if r['kind']=='registry')['assets'] += 1
        reseal(rows); self.assertTrue(validate(rows)['complete'])

    def test_missing_soft_dependency_reported_but_hard_or_used_rejected(self):
        rows = fixture(); master = json.loads(SPEC.read_text())['master']
        row = dict(kind='package_dependency', **{'from': master}, package='/Missing/Optional', hard=False, exists=False)
        rows.insert(-1, row); reseal(rows); self.assertTrue(validate(rows)['complete'])
        row['hard'] = True
        with self.assertRaises(ValueError): validate(rows)
        row.update(hard=False, exists=True)
        with self.assertRaises(ValueError): validate(rows)

    def test_scoped_inventory_and_handle_hash_contract(self):
        text = HEADER.read_text()
        registry = text.split('bool RegistryRows(bool Initial)')[1].split('bool Inventory()')[0]
        self.assertNotIn('Ledger.Package(', registry)
        self.assertIn('R.Inventory()', text)
        self.assertIn('ReadFile(H, Buffer.GetData(), Want, &Got, nullptr)', text)
        self.assertNotIn('Out.SHA1 = HashFile', text)
        self.assertIn('Physical(Target, false)', text)
        self.assertIn('WURFinalPath(H, Target)', text)
        self.assertIn('WURMappedOpen(Out.Path, *Mapping, false, Again, TargetAgain)', text)
        self.assertIn('if (P.StartsWith(TEXT("/Script/")))', text)
        self.assertIn('MissingSoftPackages.Add(P)', text)
        self.assertIn('68719476736LL - Bytes', text)
        self.assertIn('if (!ReadOnlyMapping && Prior->Mapped)', text)
        self.assertIn('FWURFile::Inspect(Path, MayBeMissing, Strict)', text)
        self.assertIn('R.Ledger.Add(ProofPath, false, WTUProofSHA1)', text)

    def test_failed_queries_and_load_observations_cannot_complete(self):
        # Even a forged terminal row with recomputed counts cannot turn an
        # observed dirty package, unpinned load or failed query into completion.
        for issue in ['dirty_after_baseline', 'unfingerprinted_loaded_package', 'load_path_or_identity_drift']:
            with self.subTest(issue=issue):
                self.reject_mutation(lambda rows: rows.insert(-1, dict(kind='load_observation', issue=issue,
                    package='/Game/Observed', phase='map:/Game/Test', normalization_attribution_claimed=False)), True)
        self.reject_mutation(lambda rows: rows.insert(-1, dict(kind='registry_query_failure',
            package='/Game/Unknown', reverse=False, dependency_type=3, query_succeeded=False)), True)

    def test_explicit_loads_have_admission_and_postload_observation(self):
        text = HEADER.read_text()
        for match in re.finditer(r'^\s*(?:auto\* M|UClass\* C|UObject\* Mesh|UPackage\* Package) = Load(?:Object[^\n]*|Package[^\n]*)', text, re.M):
            before = text[max(0, match.start()-200):match.start()]
            after = text[match.end():match.end()+260]
            self.assertIn('Ledger.BeforeLoad(', before)
            self.assertIn('Ledger.AfterLoad(', after)
        self.assertEqual(len(re.findall(r'= LoadObject<|= LoadPackage\(', text)), 4)
        self.assertIn('ConfigPresence.FindChecked(Root) != Present', text)
        self.assertIn('if (++Entries > 8192)', text)
        self.assertNotIn('.FindFiles(', text)

    def test_inventory_diagnostics_remain_failure_only(self):
        for reason in ['missing_hard_dependency', 'invalid_dependency_name', 'dependency_queue_budget',
                       'main_file_admission', 'uexp_admission', 'ubulk_admission']:
            with self.subTest(reason=reason):
                self.reject_mutation(lambda rows: rows.insert(-1, dict(kind='inventory_failure', reason=reason,
                    **{'from': '/Game/Source'}, package='/Game/Dependency', packages=1935, files=5805,
                    bytes=1000000, edges=1322, queue=1935)), True)
        text = HEADER.read_text()
        inventory = text.split('    bool Inventory()\n')[1].split('    bool Refs(')[0]
        invalid = inventory.index('TEXT("invalid_dependency_name")')
        missing = inventory.index('TEXT("missing_hard_dependency")')
        emission = inventory.index('Log.Emit(TEXT("package_dependency")')
        self.assertLess(invalid, missing)
        self.assertLess(missing, emission)
        self.assertIn('WFRStop(TEXT("usage-relevant-inventory"), R.Context)', text)

    def test_legacy_engine_compatibility(self):
        # Native module13 exposed these incompatibilities. This contract guards
        # their recurrence; Python does not compile or execute the Win32 helper.
        text = HEADER.read_text()
        self.assertNotIn('TrimStartAndEnd', text)
        self.assertNotRegex(text, r'bool\(Info\.dwFileAttributes\s*&')
        self.assertIn('((Info.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) != 0) == Directory', text)
        self.assertIn('static FString WURTrim(FString Value)', text)
        self.assertEqual(text.count('.Trim().TrimTrailing()'), 1)
        self.assertEqual(len(re.findall(r'\bWURTrim\(', text)), 4)

    def test_material_diagnostic_is_not_global_completion(self):
        rows = diagnostic_fixture()
        result = validate(rows, diagnostic=True)
        self.assertEqual(result['status'], 'valid_cohort_diagnostic')
        self.assertFalse(result['global_usage_complete'])
        with self.assertRaises(ValueError): validate(rows)
        with self.assertRaises(ValueError): validate(fixture(), diagnostic=True)
        for i in range(len(rows)):
            with self.subTest(truncated=i), self.assertRaises(ValueError): validate(rows[:i], diagnostic=True)

    def test_diagnostic_coverage_pins_and_historical_labels(self):
        mutations = [
            lambda r: r[-1].update(global_usage_complete=True),
            lambda r: r[-1].update(fresh_verify_passed=False),
            lambda r: r[-1].update(complete=True),
            lambda r: next(x for x in r if x['kind']=='historical_failure').update(revalidated=True),
            lambda r: next(x for x in r if x['kind']=='historical_failure').update(historical=False),
            lambda r: next(x for x in r if x['kind']=='historical_failure').update(package='/Different/Dependency'),
            lambda r: next(x for x in r if x['kind']=='input' and x['role']=='usage-history-report2-log').update(sha1='0'*40),
            lambda r: next(x for x in r if x['kind']=='referencer_metadata').update(native_coverage_claimed=True),
        ]
        for mutation in mutations:
            rows = diagnostic_fixture(); mutation(rows)
            with self.assertRaises((ValueError, KeyError)): validate(rows, diagnostic=True)
        for kind in ['mic', 'scope_seed', 'file', 'historical_failure']:
            rows = diagnostic_fixture(); rows.pop(next(i for i,r in enumerate(rows) if r['kind']==kind)); reseal_diagnostic(rows)
            with self.subTest(removed=kind), self.assertRaises((ValueError, KeyError)): validate(rows, diagnostic=True)
        for kind in FAILURE_KINDS:
            rows = diagnostic_fixture(); rows.insert(-1, dict(kind=kind)); reseal_diagnostic(rows)
            with self.subTest(failure=kind), self.assertRaises(ValueError): validate(rows, diagnostic=True)

    def test_diagnostic_cli_exit_and_prefix_isolation(self):
        # Synthetic log, never a claim that a native process ran.
        with tempfile.TemporaryDirectory(prefix='weapon-usage-test-') as directory:
            log = Path(directory) / 'synthetic.log'
            payload = ''.join(DIAGNOSTIC_PREFIX + json.dumps(row) + '\n' for row in diagnostic_fixture())
            log.write_text(payload)
            with self.assertRaises(ValueError): load_records(log)
            base = [sys.executable, str(Path(__file__).resolve()), '--diagnostic-log', str(log), '--native-exit-code']
            result = subprocess.run(base + ['2'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)['status'], 'valid_cohort_diagnostic')
            self.assertFalse(json.loads(result.stdout)['global_usage_complete'])
            result = subprocess.run(base + ['0'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            log.write_text(payload + PREFIX + json.dumps(fixture()[-1]) + '\n')
            result = subprocess.run(base + ['2'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            log.write_text(payload.replace('"cohort": "materials"', '"cohort": "family"'))
            result = subprocess.run(base + ['2'], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)

    def test_diagnostic_sources_preserve_prerequisite_and_abort_gates(self):
        text = HEADER.read_text(); spec = json.loads(SPEC.read_text()); recipe = json.loads((HERE/'repair.weapons.json').read_text())
        self.assertEqual(set(spec['materials_diagnostic']['prerequisite_packages']), set(recipe['original_sha1']) | set(recipe['clones'].values()))
        self.assertIn('Value != TEXT("materials")', text)
        self.assertIn('++Count != 1', text)
        self.assertIn('MaterialsDiagnostic && FString(Kind) == TEXT("complete")', text)
        self.assertIn('for (const auto& KV : Ledger.Packages) Seeds.AddUnique(KV.Key);', text)
        self.assertIn('if (Log.MaterialsDiagnostic) return true;', text)
        self.assertIn('return R.Log.Emit(TEXT("diagnostic_end"), Done) ? 2', text)
        self.assertIn('dirty_after_baseline', text)
        for pin in spec['materials_diagnostic']['history_files']:
            self.assertRegex(pin['sha1'], SHA1)

    def test_private_declaration_hashes_and_signatures(self):
        if PRIVATE is None:
            self.skipTest('pass --private-source for exact declaration validation')
        sources = {}
        for row in json.loads(resident_bytes(PRIVATE / 'usage-api-extra/declaration-pins.json')):
            # Captured local paths are workspace-relative; use the declared
            # basename beneath this explicitly selected capture directory.
            p = PRIVATE / 'usage-api-extra' / Path(row['local']).name
            data = resident_bytes(p)
            self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'])
            self.assertEqual(len(data), row['bytes'])
            sources[Path(row['relative']).name] = data.decode('utf-8-sig')
        legacy_string = resident_bytes(PRIVATE / 'usage-api-extra/UnrealString.h')
        self.assertEqual(len(legacy_string), 65902)
        self.assertEqual(hashlib.sha256(legacy_string).hexdigest(),
                         'c202aab367e3280755e9ded356045c3326d99d7d4d4cda715636e073186f7a7e')
        string_declarations = legacy_string.decode('utf-8-sig')
        self.assertRegex(string_declarations, r'FString\s+Trim\(\s*\)\s*;')
        self.assertRegex(string_declarations, r'FString\s+TrimTrailing\(\s*void\s*\)\s*;')
        registry = sources['IAssetRegistry.h']
        for name in ['GetAllAssets', 'GetDependencies', 'GetReferencers', 'GetAssetsByPackageName']:
            self.assertRegex(registry, r'virtual bool ' + name + r'\(')
        self.assertIn('GetDerivedClassNames', registry)
        self.assertIn('FAssetData::GetTagValue<FString>', sources['AssetData.h'])
        self.assertRegex(sources['UObjectAnnotation.h'], r'const TMap<const UObjectBase\s*\*,\s*TAnnotation>& GetAnnotationMap\(\) const')
        self.assertRegex(sources['AssetRegistryInterface.h'], r'Packages\s*=\s*\(Type\)\s*\(Soft\s*\|\s*Hard\)')

    def test_private_capture_hashes_and_api_semantics(self):
        if PRIVATE is None:
            self.skipTest('pass --private-source=<weapon-sampler-review> for pinned API tests')
        sources = {}
        for manifest in ['usage-api/local-pins.json', 'usage-source/pins.json', 'usage-api-extra/pins.json', 'usage-api-extra/supplement-pins.json']:
            p = PRIVATE / manifest
            rows = json.loads(resident_bytes(p))
            if isinstance(rows, dict):
                rows = [dict(file=f, sha256=h) for f,h in rows.items()]
            for row in rows:
                if row.get('missing'):
                    continue
                name = row.get('local', row.get('file'))
                data = resident_bytes(p.parent / name)
                self.assertEqual(hashlib.sha256(data).hexdigest(), row['sha256'], name)
                if 'size' in row or 'bytes' in row:
                    self.assertEqual(len(data), row.get('size', row.get('bytes')))
                sources[name.split('__')[-1]] = data.decode('utf-8-sig')
        self.assertIn('const FMeshMapBuildData* UMapBuildDataRegistry::GetMeshBuildData', sources['MapBuildData.cpp'])
        lookup = re.search(r'const FMeshMapBuildData\*\s+UMapBuildDataRegistry::GetMeshBuildData[^\{]*\{([^}]+)', sources['MapBuildData.cpp'])
        self.assertIsNotNone(lookup)
        self.assertRegex(lookup[1], r'\bFind\s*\(')
        self.assertNotRegex(lookup[1], r'\b(?:Add|Allocate|MarkPackageDirty)\s*\(')
        self.assertRegex(sources['StaticMeshComponent.cpp'], r'GComponentsWithLegacyLightmaps\s*\.\s*AddAnnotation')
        self.assertIn('CreateRecordIterator()', sources['InheritableComponentHandler.h'])
        self.assertIn('UFUNCTION(BlueprintNativeEvent)\n\tUMeshComponent* GetPickupMeshTemplate', sources['UTInventory.h'])

    def test_native_log_if_supplied(self):
        if NATIVE_LOG is None:
            self.skipTest('no native execution claimed; pass --native-log for actual report validation')
        self.assertEqual(NATIVE_EXIT_CODE, 0, 'recorded native exit code 0 is required alongside the complete log')
        validate(load_records(NATIVE_LOG))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--private-source', type=Path)
    parser.add_argument('--native-log', type=Path)
    parser.add_argument('--diagnostic-log', type=Path)
    parser.add_argument('--native-exit-code', type=int)
    args, remaining = parser.parse_known_args()
    if args.diagnostic_log is not None:
        try:
            require(args.native_log is None and not remaining, 'diagnostic validation is a separate entry point')
            require(args.native_exit_code == 2, 'recorded diagnostic native exit 2 required')
            result = validate(load_records(args.diagnostic_log, DIAGNOSTIC_PREFIX), diagnostic=True)
            print(json.dumps(result, sort_keys=True))
        except (ValueError, KeyError, TypeError, OSError) as error:
            print(json.dumps({'status': 'invalid_or_aborted_diagnostic', 'global_usage_complete': False, 'error': str(error)}))
            sys.exit(1)
        sys.exit(2)
    PRIVATE, NATIVE_LOG, NATIVE_EXIT_CODE = args.private_source, args.native_log, args.native_exit_code
    unittest.main(argv=[sys.argv[0]] + remaining)
