#!/usr/bin/env python3
"""Close the idle tabs the pipeline left behind in the Herdr spaces.

  garbage_tabs.py            close them
  garbage_tabs.py --dry      only list what would be closed

A tab is garbage only when ALL of these hold:
  - it is in one of the stage spaces (stages.<x>.space in config.json);
  - it is not the space's first tab (the queue monitor lives there) nor a seat (label `vaga`);
  - it has a single pane;
  - no coding agent runs in that pane (idle, done or otherwise);
  - the pane's title is the shell prompt's ("user@host:cwd"), i.e. no
    command is running in the foreground.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[2] / "esteira" / "config.json"
SPACES = tuple(st["space"] for st in json.loads(CONFIG.read_text())["stages"].values())
SHELL_TITLE = re.compile(r"^[^\s@]+@[^\s:]+:")


def herdr(*args):
    r = subprocess.run(["herdr", *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"herdr {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    return json.loads(r.stdout)["result"]


def main(dry):
    workspaces = [w for w in herdr("workspace", "list")["workspaces"] if w["label"] in SPACES]
    closed, kept = [], []
    for ws in workspaces:
        tabs = herdr("tab", "list", "--workspace", ws["workspace_id"])["tabs"]
        panes = herdr("pane", "list", "--workspace", ws["workspace_id"])["panes"]
        first = min(t["number"] for t in tabs)
        for tab in tabs:
            if tab["number"] == first or tab["label"] == "vaga":
                continue  # the monitor, or a pipeline seat (its Claude is brought back by the dispatcher)
            mine = [p for p in panes if p["tab_id"] == tab["tab_id"]]
            idle_shell = (len(mine) == 1 and not mine[0].get("agent")
                          and SHELL_TITLE.match(mine[0].get("terminal_title_stripped") or ""))
            where = f"{ws['label']} / aba {tab['number']} ({tab['label']})"
            if not idle_shell:
                why = "agente" if any(p.get("agent") for p in mine) else "processo rodando ou várias panes"
                names = {a["pane_id"]: a.get("name") for a in herdr("agent", "list")["agents"]}
                if why == "agente" and not names.get(mine[0]["pane_id"]):
                    why = "agente SEM NOME (órfão? o supervisor adota ou recicla)"
                kept.append(f"{where}: {why}")
                continue
            if not dry:
                herdr("tab", "close", tab["tab_id"])
            closed.append(where)
    print(json.dumps({"dry": dry, "closed": closed, "kept": kept}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main("--dry" in sys.argv[1:])
