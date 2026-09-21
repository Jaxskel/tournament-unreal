#!/usr/bin/env python3
"""Validate native first-five material reports; emit review evidence, never assets."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re

SPEC = Path(__file__).with_name('report.materials-first5.json')
PREFIX = 'COMPAT_MATERIAL_REPORT '
ROOTS = {'BaseColor', 'EmissiveColor', 'Opacity', 'OpacityMask', 'Normal', 'WorldPositionOffset',
         'WorldDisplacement', 'Refraction', 'MaterialAttributes'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def object_path(package):
    return package + '.' + package.rsplit('/', 1)[1]


def finite(value):
    if isinstance(value, float):
        require(math.isfinite(value), 'non-finite report value')
    elif isinstance(value, dict):
        for v in value.values():
            finite(v)
    elif isinstance(value, list):
        for v in value:
            finite(v)


def read_log(text):
    records, completed = [], False
    for line in text.splitlines():
        if PREFIX not in line:
            continue
        require(not completed, 'report records after completion')
        row = json.loads(line.split(PREFIX, 1)[1])
        require(row.get('schema') == 'ut4-material-report-v1', 'unknown native report schema')
        if row.get('kind') == 'complete':
            require(row.get('read_only') is True and row.get('count') == 11 and len(records) == 11,
                    'invalid completion/count')
            completed = True
        else:
            require(row.get('kind') == 'material', 'unknown native record kind')
            records.append(row)
    require(completed, 'missing native completion: failed or incomplete Report')
    return records


def canonical(value):
    """Order metadata sets without erasing meaningful pin/override values."""
    if isinstance(value, dict):
        return {k: canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        items = [canonical(v) for v in value]
        # Generic list sorting would erase ordered parent chains, vectors and masks.
        return items
    return value


def pin_valid(pin, label, paths):
    require(isinstance(pin, dict), label + ': missing pin')
    expr = pin.get('expression')
    require(isinstance(expr, str) and (not expr or expr in paths), label + ': dangling expression')
    index = pin.get('output_index')
    # UE4.15 function-call inputs use INDEX_NONE until connected (MaterialExpressions.cpp:8316).
    require(type(index) is int and (index >= 0 or (not expr and index == -1)), label + ': invalid output index')
    masks = pin.get('mask')
    require(isinstance(masks, list) and len(masks) == 5 and all(type(v) is int for v in masks),
            label + ': missing native channel-mask evidence')


def validate(records, spec=None):
    spec = spec or json.loads(SPEC.read_text())
    require(spec.get('schema') == 'ut4-material-preflight-first5-v1' and spec.get('read_only') is True,
            'read-only first-five spec required')
    targets = {object_path(t['package']): t for t in spec['targets']}
    require(len(targets) == 11 and len(records) == 11, 'exactly eleven targets required')
    actual = {}
    for r in records:
        finite(r)
        path = r.get('material')
        require(path in targets and path not in actual, 'unexpected or duplicate material: ' + str(path))
        actual[path] = r
    require(actual.keys() == targets.keys(), 'missing target')
    consistent_hashes = {}
    for path, t in targets.items():
        r = actual[path]
        for key in ('class', 'blend', 'shading'):
            require(r.get(key) == t['expected_' + key], path + ': unexpected ' + key)
        require(r.get('registry_scan_complete') is True, path + ': incomplete registry scan')
        require(r.get('package_dirty_after_load') is False, path + ': package dirtied during load; inspect before repair')
        for key in ('properties', 'package_sha1', 'roots'):
            require(isinstance(r.get(key), dict), path + ': missing ' + key)
        for key in ('nodes', 'parent_chain', 'scalar_parameters', 'vector_parameters', 'texture_parameters',
                    'direct_referencers', 'transitive_referencers'):
            require(isinstance(r.get(key), list), path + ': missing ' + key)
        require(type(r.get('two_sided')) is bool and isinstance(r.get('opacity_mask_clip'), (int, float)),
                path + ': missing effective render settings')
        chain = r['parent_chain']
        require(chain and chain[0] == path and len(chain) == len(set(chain)), path + ': invalid parent chain')
        require(chain[-1] == r.get('base_material') and chain[-1] in targets and targets[chain[-1]]['role'] == 'parent',
                path + ': base outside five-parent scope')
        if t['role'] == 'parent':
            require(chain == [path], path + ': expected direct material')
            require(set(r['roots']) == ROOTS, path + ': incomplete root coverage, including refraction/displacement')
        else:
            require(len(chain) >= 2 and all(p in targets for p in chain), path + ': parent outside selected set')
            if t['expected_parent']:
                require(chain[1] == t['expected_parent'], path + ': changed immediate parent')
            else:
                # Core_Inst is newly reported; do not infer success if it points elsewhere.
                require(chain[1] == object_path(t['package'].removesuffix('_Inst')), path + ': unexpected Core instance parent')
            for key in ('ScalarParameterValues', 'VectorParameterValues', 'TextureParameterValues', 'FontParameterValues', 'BasePropertyOverrides'):
                require(key in r['properties'] and isinstance(r['properties'][key], str), path + ': missing raw ' + key)
            for key in ('static_overrides', 'static_effective'):
                require(isinstance(r.get(key), dict) and set(r[key]) == {'switches', 'masks', 'terrain'}, path + ': missing ' + key)
        for p in chain:
            require(p.split('.')[0] in r['package_sha1'], path + ': parent package hash missing')
        require(all(isinstance(v, str) and re.fullmatch(r'[0-9a-fA-F]{40}', v) for v in r['package_sha1'].values()), path + ': invalid package SHA-1')
        for pkg, digest in r['package_sha1'].items():
            require(pkg not in consistent_hashes or consistent_hashes[pkg] == digest, path + ': inconsistent package hash across records')
            consistent_hashes[pkg] = digest
        nodes = r['nodes']
        paths = {n['path'] for n in nodes}
        require(len(paths) == len(nodes), path + ': duplicate graph node')
        own = {n['name']: n for n in nodes if n.get('owner') == path}
        for n in nodes:
            require(n.get('class', '').startswith('MaterialExpression') and isinstance(n.get('properties'), dict), path + ': missing node metadata')
            for pin in n['inputs']:
                pin_valid(pin, n['path'], paths)
            if n.get('function'):
                require(n['function'].split('.')[0] in r['package_sha1'], path + ': function package hash missing')
        for key, pin in r['roots'].items():
            pin_valid(pin, path + ':' + key, paths)
        for edge, expected in t['assert_edges'].items():
            if '.' in edge:
                node_name, input_name = edge.split('.', 1)
                require(node_name in own, path + ': absent ' + node_name)
                pins = [p for p in own[node_name]['inputs'] if p['name'] == input_name]
                require(len(pins) == 1, path + ': ambiguous/missing pin ' + edge)
                pin = pins[0]
            else:
                require(edge in r['roots'], path + ': missing root ' + edge)
                pin = r['roots'][edge]
            require(expected in own and pin['expression'] == own[expected]['path'], path + ': edge mismatch ' + edge)
            require(own[expected]['class'] == expected.rsplit('_', 1)[0], path + ': unexpected expression class ' + expected)
        for collection in ('scalar_parameters', 'vector_parameters', 'texture_parameters'):
            require(all('name' in p and 'value' in p for p in r[collection]), path + ': incomplete parameter')
        for v in r['vector_parameters']:
            require(isinstance(v['value'], list) and len(v['value']) == 4, path + ': vector requires RGBA including HDR alpha')
    # Stable native ordering for metadata sets; retain parent-chain/vector/pin ordering.
    for r in actual.values():
        for key in ('nodes',):
            r[key] = sorted(r[key], key=lambda x: x['path'])
        for key in ('scalar_parameters', 'vector_parameters', 'texture_parameters'):
            r[key] = sorted(r[key], key=lambda x: x['name'])
        for key in ('direct_referencers', 'transitive_referencers'):
            r[key] = sorted(r[key])
    return canonical({'schema': 'ut4-material-review-snapshot-v1', 'apply_ready': False,
                      'spec_sha256': hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest(),
                      'review_required': spec['limitations'], 'materials': [actual[p] for p in sorted(actual)]})


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report-log', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True, help='New local review snapshot, never an asset')
    parser.add_argument('--baseline', type=Path, help='Previously reviewed snapshot; any drift fails')
    args = parser.parse_args(argv)
    try:
        result = validate(read_log(args.report_log.read_text(encoding='utf-8-sig')))
        if args.baseline:
            require(result == json.loads(args.baseline.read_text()), 'baseline drift: compare graph pins, properties, overrides, hashes and dependents; do not Apply')
        # Exclusive creation protects prior evidence and prevents accidental asset replacement.
        require(args.out.suffix == '.json', 'output must be a new .json review snapshot')
        with args.out.open('x', encoding='utf-8') as f:
            json.dump(result, f, indent=2, allow_nan=False)
            f.write('\n')
    except (ValueError, KeyError, TypeError, OSError) as e:
        parser.exit(1, str(e) + '\n')
    print('11 material reports validated; review snapshot only, apply_ready=false. No assets changed.')


if __name__ == '__main__':
    main()
