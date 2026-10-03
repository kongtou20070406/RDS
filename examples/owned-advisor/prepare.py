"""Prepare a frozen two-step CPU research workflow with automatic result intake."""
import argparse
import importlib.util
import json
from pathlib import Path


def prepare(root):
    module = importlib.util.spec_from_file_location(
        'project_runner_example', Path(__file__).resolve().parents[1] / 'project-runner' / 'prepare.py')
    base = importlib.util.module_from_spec(module)
    module.loader.exec_module(base)
    result = base.prepare(root)
    root = Path(result['root'])
    contract = json.loads((root / 'contract.json').read_text(encoding='utf-8'))
    manifests = [json.loads(Path(path).read_text(encoding='utf-8')) for path in result['manifests']]
    nodes = []
    for arm in ('control', 'treatment'):
        action = {'id': 'measure-' + arm, 'kind': 'PAIRED_TEST',
                  'description': 'Measure the frozen ' + arm + ' on the demonstration dataset',
                  'competing_explanations': ['linear relation fits', 'residual needs another representation'],
                  'required_observables': [arm + '_mse'],
                  'outcomes': [{'observation': 'low residual', 'next_decision': 'retain the scoped fit'},
                               {'observation': 'high residual', 'next_decision': 'review the representation'}]}
        conditions = [] if arm == 'control' else [
            {'fact': 'run.control.succeeded', 'value': True},
            {'fact': 'control_mse', 'op': 'gt', 'value': 0.01}]
        nodes.append({'id': arm + '-route', 'executable': {
            'decisions': ['fit-demo'], 'preconditions': conditions, 'action': action}})
    contract['advisor_policy'] = {
        'schema': 1,
        'context': {'research_mode': 'empirical', 'decision': {
            'id': 'fit-demo', 'goal_revision': 'demo-v1', 'scope': {'dataset': 'six synthetic rows'},
            'goal_conditions': [{'fact': 'treatment_mse', 'op': 'lte', 'value': 0.01}]}},
        'graph': {'nodes': nodes, 'edges': []},
        'routes': [{'candidate': 'measure-' + manifest['id'], 'manifest': manifest} for manifest in manifests],
        'observations': [{'fact': arm + '_mse', 'run_id': arm, 'path': 'outputs/' + arm + '.json',
                          'selector': {'pointer': '/mse'}, 'format': 'json'} for arm in ('control', 'treatment')]}
    (root / 'contract.json').write_text(json.dumps(contract, indent=2), encoding='utf-8')
    return {**result, 'mode': 'program-owned', 'scientific_support': 'UNKNOWN'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    print(json.dumps(prepare(parser.parse_args().root), indent=2))
