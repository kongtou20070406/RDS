"""Keep reasoning dependencies and structured rules across optional YAML setups."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from rds_meta import dump_simple_yaml, parse_simple_yaml


class GraphIOTests(unittest.TestCase):
    def test_dependency_edges_never_become_nodes_and_bindings_survive_save(self):
        graph = parse_simple_yaml((ROOT / 'references/judgment-graph.yaml').read_text(encoding='utf-8'))
        self.assertTrue(graph['edges'])
        self.assertTrue(all(isinstance(node.get('id'), str) for node in graph['nodes']))
        self.assertEqual(len(graph['nodes']), len({node['id'] for node in graph['nodes']}))
        bound = [node for node in graph['nodes'] if 'executable' in node]
        self.assertTrue(bound)
        restored = parse_simple_yaml(dump_simple_yaml(graph))
        self.assertEqual(restored['edges'], graph['edges'])
        self.assertEqual(restored['nodes'], graph['nodes'])

    def test_commas_in_sources_are_preserved_as_one_locator(self):
        graph = parse_simple_yaml('nodes:\n  - id: n\n    sources: ["source, with comma", "another"]\nedges: []\n')
        self.assertEqual(graph['nodes'][0]['sources'], ['source, with comma', 'another'])
        self.assertEqual(parse_simple_yaml(dump_simple_yaml(graph)), graph)


if __name__ == '__main__':
    unittest.main()
