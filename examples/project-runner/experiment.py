"""Small CPU demonstration: fit a constant or a line to a recorded dataset."""
import argparse
import csv
import json
from pathlib import Path

from evaluate import mean_squared_error


parser = argparse.ArgumentParser()
parser.add_argument("--arm", choices=("control", "treatment"), required=True)
parser.add_argument("--output", required=True)
args = parser.parse_args()
config = json.loads(Path("config.json").read_text(encoding="utf-8"))
with Path(config["data"]).open(newline="", encoding="utf-8") as stream:
    rows = [(float(r["x"]), float(r["y"])) for r in csv.DictReader(stream)]
x_mean = sum(x for x, _ in rows) / len(rows)
y_mean = sum(y for _, y in rows) / len(rows)
slope = 0.0
if args.arm == "treatment":
    slope = sum((x - x_mean) * (y - y_mean) for x, y in rows) / sum((x - x_mean) ** 2 for x, _ in rows)
intercept = y_mean - slope * x_mean
result = {"demo": True, "arm": args.arm, "n": len(rows), "slope": slope,
          "intercept": intercept, "mse": mean_squared_error(rows, slope, intercept),
          "scope": "finite recorded demonstration data; no generalization claim"}
Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
print(json.dumps(result, allow_nan=False))
