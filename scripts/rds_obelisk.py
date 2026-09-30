"""Read-only bridge to the installed Obelisk CLI and CodeAct sandbox.

No database access, history mirror, embedding store or automatic memory writes.
The caller supplies a unique literal query path so Obelisk can identify invocation.
"""
import json
import shutil
import subprocess
from pathlib import Path, PureWindowsPath


def query_source(project_path, terms, offset=0):
    if not project_path or not (Path(project_path).is_absolute() or PureWindowsPath(project_path).is_absolute()):
        raise ValueError("An exact absolute project_path is required")
    if not terms or offset < 0:
        raise ValueError("Use a short topic query and a nonnegative session offset")
    # JSON quoting is for JavaScript source, never shell interpolation.
    return f"""const path = {json.dumps(project_path)};
const offset = {offset};
const rows = sql('SELECT id, title FROM sessions WHERE project_path = ? ORDER BY ended_at DESC, id DESC LIMIT 6 OFFSET ?', path, offset);
const total = sql('SELECT COUNT(*) AS n FROM sessions WHERE project_path = ?', path)[0].n;
return {{scope:path,total_sessions:total,next_offset:offset+rows.length<total?offset+rows.length:null,
  evidence:rows.map(s=>({{session:s,hits:search({json.dumps(terms)},{{sessionId:s.id,limit:4}})}}))}};
"""


def history_command(args):
    if args.subcommand == "prepare":
        if args.uuid:
            if args.raw_offset < 0:
                raise ValueError("Raw offset must be nonnegative")
            uid = json.dumps(args.uuid)
            source = f"return {{context:context({uid}),raw:raw({uid},{{offset:{args.raw_offset},limit:10000}})}};\n"
        else:
            source = query_source(args.project_path, args.terms, args.offset)
        path = Path(args.output).resolve()
        with path.open("x", encoding="utf-8") as handle:
            handle.write(source)
        print(path)
    elif args.subcommand == "query":
        executable = shutil.which("obelisk")
        if not executable:
            raise ValueError("Obelisk CLI is unavailable; history has not been checked")
        path = Path(args.query).resolve(strict=True)
        # Inherit output: provenance, visibility and paging are not summarized away.
        result = subprocess.run([executable, "--query", str(path)], timeout=60)
        if result.returncode:
            raise ValueError(f"Obelisk failed with exit {result.returncode}; do not infer that history is absent")
    else:
        raise ValueError("Choose history prepare or history query")
