"""Synthetic continuation trace; counts serialized bytes, not LLM tokens or latency."""
import json
from pathlib import Path
import platform
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from rds_project import canonical
from rds_tms_store import current, tms_tool


def size(value):
    return len(canonical(value).encode('utf-8'))


def run():
    claims = {'claim-' + str(i): {'status': 'supported', 'source': 'synthetic observation ' + str(i),
                                 'description': 'Synthetic scoped claim ' + str(i)} for i in range(50)}
    initial = {'claims': claims, 'rules': [{'from': list(claims), 'to': 'target', 'status': 'supported',
                                          'source': 'synthetic AND implication'}], 'goal': 'target'}
    changes = [{'retract_nodes': ['claim-0']},
               {'declaration': {'claims': {'claim-0': {'status': 'supported', 'source': 'new synthetic observation'}}}}]
    totals = {'delta_input_bytes': 0, 'whole_map_input_bytes': 0,
              'brief_output_bytes': 0, 'full_output_bytes': 0}
    statuses = []
    with tempfile.TemporaryDirectory() as root:
        tms_tool(root, declaration=initial)
        for action in changes:
            totals['delta_input_bytes'] += size(action)
            totals['whole_map_input_bytes'] += size({'dependency_map': current(root)['dependency_map'], **action})
            observation = tms_tool(root, **action)
            full = json.loads(Path(observation['record']).read_text(encoding='utf-8'))
            totals['brief_output_bytes'] += size(observation)
            totals['full_output_bytes'] += size(full)
            statuses.append(observation['goals']['target'])
    return {'scope': 'Synthetic serialized continuation transport; no live LLM or SDK/harness invocation',
            'environment': {'python': platform.python_version(), 'os': platform.system()},
            'workload': {'claims': 50, 'rules': 1, 'continuation_actions': 2, 'program_tool_calls': 2},
            'goal_statuses': statuses, **totals,
            'limits': 'Excludes initial declaration and setup; full-table replay is a serialization comparator. '
                      'Bytes are not billed tokens, scientific gain, or measured end-to-end latency.'}


if __name__ == '__main__':
    print(json.dumps(run(), indent=2))
