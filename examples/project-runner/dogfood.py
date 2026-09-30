"""Developer tool: run a configured, local RDS unittest selection without a shell."""
import json
from pathlib import Path
import subprocess
import sys


config = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
result = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s",
                         config["test_directory"], "-p", config["pattern"], "-v"],
                        cwd=Path.cwd(), shell=False)
sys.exit(result.returncode)
