"""Print the synthetic bounded-search example; performs no training or writes."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from rds_meta import load_judgment_graph
from rds_advisor_search import search_directions

_, graph = load_judgment_graph(ROOT / "references/judgment-graph.yaml")
context = json.loads(Path(__file__).with_name("boundary-context.json").read_text(encoding="utf-8"))
print(json.dumps(search_directions(graph, context), ensure_ascii=False, indent=2))
