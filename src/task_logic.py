"""Collect observations for one pure-code candidate; no acceptance judgment."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
sys.path.insert(0, str(WORKSPACE / 'cog-workbench/src'))
from workbench_suite import Suite, digest, package_digest, require


def check_input(bundle):
    import cog_core
    criteria = {c['id'] for c in bundle.get('author_request', {}).get('contract', {}).get('acceptance_criteria', [])}
    requested = bundle.get('test_criterion_ids', [])
    if len(set(requested)) != len(requested) or not set(requested) <= criteria:
        return [cog_core.problem('evidence-criteria', 'Declared-test evidence must cite unique accepted criterion IDs.')]
    reference = bundle.get('reference')
    if reference and reference['criterion_id'] not in criteria:
        return [cog_core.problem('evidence-criteria', 'Reference comparison cites an unknown criterion.')]
    return []


def compare_reference(reference, snapshot, root, suite):
    other = suite.root(reference['path'])
    require(other != root, 'Reference must be a separate package.')
    manifest = suite.manifest(other)
    require(manifest.get('kind') == 'code' and not manifest.get('requires') and not manifest.get('reaches'), 'Reference must be pure code.')
    require(package_digest(other) == reference['package_sha256'], 'Reference package changed.')
    paths = {f['path'] for f in snapshot['files']}
    require(reference['fixture_path'] in paths, 'Reference cases must be part of the authored snapshot.')
    fixtures = json.loads(suite.file(root, reference['fixture_path']).read_text())
    require(isinstance(fixtures, list) and 0 < len(fixtures) <= 100, 'Reference comparison requires 1–100 named bundle fixtures.')
    records = []
    candidate_sha = package_digest(root)
    for fixture in fixtures:
        require(isinstance(fixture, dict) and isinstance(fixture.get('name'), str) and isinstance(fixture.get('bundle'), dict), 'Each comparison fixture requires name and bundle.')
        row = {'case': fixture['name'], 'input': fixture['bundle'], 'outputs': {}}
        for label, package in [('candidate', root), ('reference', other)]:
            m = suite.manifest(package)
            tasks = [i['task'] for i in m['interfaces'] if i.get('audience') == 'usage' and i.get('default')]
            require(len(tasks) == 1, 'Comparison package needs one default usage task.')
            temp, files = suite.documents({'bundle': fixture['bundle']})
            with temp:
                raw = suite.call(package, tasks[0], ['--bundle', files['bundle']], expect_json=False, stdout_limit=None)
            result = json.loads(raw['stdout'])
            require(result.get('envelope') == 1 and result.get('cog') == {'id': m['id'], 'version': str(m['version'])}
                    and isinstance(result.get('ok'), bool) and isinstance(result.get('problems'), list), 'Comparison did not observe the declared envelope.')
            require(raw['exit_code'] == 0 or result['ok'] is False, 'Comparison exit contradicts its envelope.')
            row['outputs'][label] = result
        def normalized(value):
            return {'ok': value['ok'], 'payload': value['payload'], 'error_code': (value['error'] or {}).get('code'),
                    'problems': sorted({(p['check'], p['severity']) for p in value['problems']})}
        row['normalized_match'] = normalized(row['outputs']['candidate']) == normalized(row['outputs']['reference'])
        row['full_problems_match'] = row['outputs']['candidate']['problems'] == row['outputs']['reference']['problems']
        records.append(row)
        require(package_digest(root) == candidate_sha and package_digest(other) == reference['package_sha256'], 'Package changed during reference comparison.')
    return {'reference': {'path': str(other), 'id': manifest['id'], 'package_sha256': reference['package_sha256']},
            'cases': records, 'scope': 'Actual comparison observations; normalized matches compare payload, ok, error code and problem check/severity, excluding identity and prose. Full envelopes and diagnostic-prose comparison are retained. Observation is not acceptance.'}


def verify(bundle, suite):
    materialized = bundle['materialized']
    root = suite.root(materialized['path'])
    expected_package = materialized['package_sha256']
    require(package_digest(root) == expected_package, 'Candidate changed after materialization.')
    snapshot = suite.source_snapshot(bundle['author_request'], bundle['author_envelope'])
    source_sha = digest({'contract': snapshot['contract'], 'files': sorted(snapshot['files'], key=lambda f: f['path'])})
    require(source_sha == materialized['source_sha256'], 'Materialization and author source disagree.')
    require(snapshot['contract'].get('kind') == 'code', 'Only pure code candidate execution is supported.')
    for row in snapshot['files']:
        require(suite.file(root, row['path']).read_text() == row['content'], 'Candidate source differs from author snapshot.')
    manifest = suite.manifest(root)
    require(manifest.get('kind') == 'code' and not manifest.get('reaches') and not manifest.get('requires'), 'Candidate is not pure code.')
    tests = suite.verify(root, 'test')
    require(package_digest(root) == expected_package, 'Candidate package changed while tests executed.')
    observations = suite.evaluate(root, bundle['author_request'], bundle['author_envelope'], bundle['plan_envelope'])
    require(observations['package_sha256'] == expected_package, 'Case execution used a different package.')
    review = observations['review_request']
    for criterion in bundle['test_criterion_ids']:
        review['evidence'].append({'id': 'declared-tests:' + criterion, 'criterion_id': criterion,
            'candidate_sha256': source_sha, 'kind': 'execution',
            'status': 'passed' if tests['exit_code'] == 0 else 'failed',
            'text': json.dumps({'record': tests, 'scope': 'Declared test suite execution only. The caller links it to this criterion; inspect supplied test source and actual observations for coverage. Exit zero does not prove every criterion. No PYTHONPATH override or automatic environment installation.'})})
    if bundle.get('reference'):
        comparison = compare_reference(bundle['reference'], snapshot, root, suite)
        review['evidence'].append({'id': 'reference-comparison', 'criterion_id': bundle['reference']['criterion_id'],
            'candidate_sha256': source_sha, 'kind': 'execution', 'status': 'passed', 'text': json.dumps(comparison)})
    return {'review_request': review, 'tests': tests, 'case_record': observations['record_path'],
            'source_sha256': source_sha, 'package_sha256': expected_package,
            'status': 'observed-awaiting-review', 'authority_use': []}


def run(bundle, grant, journal):
    return verify(bundle, Suite(workspace=WORKSPACE)), []


def check_output(payload, bundle):
    import cog_core
    if any(e['candidate_sha256'] != payload['source_sha256'] for e in payload['review_request']['evidence']):
        return [cog_core.problem('evidence-identity', 'Evidence belongs to a different candidate.')]
    return []
