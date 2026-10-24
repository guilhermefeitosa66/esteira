"""Shared helpers for the pipeline scripts (dispatch, supervise, worker, status).

Config is read fresh on every call to `cfg()`, so a long-running loop picks up
an edit on its next pass, and a half-written or invalid file is refused (the
pass is skipped) instead of being used with stale values.

Seats
-----
Each stage owns a Herdr space (`stages.<x>.space`). Tab 1 of the space is the
queue monitor; every other tab is a *seat*: one Claude kept open for good,
named `<agent_prefix>-<stage>-<k>` (k = 1..max). The dispatcher `/clear`s an idle seat and
prompts it with the stage's skill; the worker gives the seat back with
`worker.py end`. A seat is never closed to finish a job.
"""
import fcntl
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONFIG = HERE.parent / "config.json"
REPO_DIR = HERE.parents[2]
SEAT_LABEL = "vaga"
REQUIRED = ("repo", "stages", "state_dir", "max_workers", "timeouts", "min_free_ram_gb")


class ConfigError(Exception):
    pass


def cfg():
    try:
        c = json.loads(CONFIG.read_text())
    except (OSError, ValueError) as e:
        raise ConfigError(f"config.json unreadable: {e}")
    missing = [k for k in REQUIRED if k not in c]
    if missing:
        raise ConfigError(f"config.json missing {missing}")
    for key, st in c["stages"].items():
        for f in ("queue", "active", "skill", "next", "max", "space"):
            if f not in st:
                raise ConfigError(f"stage {key} missing {f}")
    return c


def state_dir():
    c = json.loads(CONFIG.read_text())
    p = Path(os.path.expanduser(c["state_dir"]))
    p.mkdir(parents=True, exist_ok=True)
    return p


def load(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def save(path, data):
    """Atomic write: a reader never sees half a file."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    os.replace(tmp, path)


def log(msg, quiet=False):
    line = time.strftime("%Y-%m-%d %H:%M:%S ") + msg
    if not quiet:
        print(line, flush=True)
    with (state_dir() / "dispatch.log").open("a") as f:
        f.write(line + "\n")


@contextmanager
def pipeline_lock():
    """One dispatcher/supervisor pass at a time, machine-wide."""
    with (state_dir() / "dispatch.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


# --- Herdr -------------------------------------------------------------------

def herdr(*args, check=True):
    r = subprocess.run(["herdr", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"herdr {' '.join(args)}: {r.stderr.strip() or r.stdout.strip()}")
    try:
        return json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}
    except ValueError:
        return {}


def require_herdr():
    if os.environ.get("HERDR_ENV") != "1":
        sys.exit("must run inside a Herdr pane (HERDR_ENV=1)")


def workspace_by_label(label):
    for w in herdr("workspace", "list")["result"]["workspaces"]:
        if w["label"] == label:
            return w["workspace_id"]
    return None


def agents():
    return herdr("agent", "list")["result"]["agents"]


def tabs(ws):
    return herdr("tab", "list", "--workspace", ws)["result"]["tabs"]


def panes(ws):
    return herdr("pane", "list", "--workspace", ws)["result"]["panes"]


def read_pane(pane, lines=None):
    args = ["pane", "read", pane, "--source", "recent-unwrapped" if lines else "visible"]
    if lines:
        args += ["--lines", str(lines)]
    r = subprocess.run(["herdr", *args], capture_output=True, text=True)
    return r.stdout


def input_line(screen):
    """Text sitting in Claude's input box (the last `❯` line), '' if empty."""
    for line in reversed(screen.splitlines()):
        s = line.strip()
        if s.startswith("❯"):
            return s[1:].strip()
    return ""


BG_RE = re.compile(r"\b(\d+) (shells?|monitors?|local agents?|background tasks?)\b")


def background_tasks(screen):
    """Claude's footer says '· 1 shell, 1 monitor' while background work runs."""
    tail = "\n".join(screen.splitlines()[-4:])
    return sum(int(m.group(1)) for m in BG_RE.finditer(tail))


def seats(stage_key, c=None):
    """The stage's seat tabs: [{tab, pane, number, label, agent}] (tab 1 excluded)."""
    c = c or cfg()
    ws = workspace_by_label(c["stages"][stage_key]["space"])
    if not ws:
        return None, []
    tab_list = sorted(tabs(ws), key=lambda t: t["number"])
    if not tab_list:
        return ws, []
    first = tab_list[0]["number"]
    by_tab = {}
    for p in panes(ws):
        by_tab.setdefault(p["tab_id"], []).append(p)
    named = {a["pane_id"]: a for a in agents()}
    out = []
    for t in tab_list:
        if t["number"] == first:
            continue
        ps = by_tab.get(t["tab_id"], [])
        if len(ps) != 1:
            continue
        p = ps[0]
        out.append({"tab": t["tab_id"], "pane": p["pane_id"], "number": t["number"],
                    "label": t["label"], "agent": named.get(p["pane_id"]),
                    "title": p.get("terminal_title_stripped") or ""})
    return ws, out


def wait_agent_ready(pane, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        got = herdr("agent", "get", pane, check=False)
        status = (got.get("result") or {}).get("agent", {}).get("agent_status")
        if status in ("idle", "done"):
            time.sleep(2)  # the TUI keeps drawing for a moment after it reports idle
            return True
        time.sleep(2)
    return False


def seat_name(stage_key, k, c=None):
    return f"{(c or cfg()).get('agent_prefix', 'es')}-{stage_key}-{k}"


def start_claude(pane):
    herdr("pane", "run", pane, cfg().get("claude_command", "claude --dangerously-skip-permissions"))
    if not wait_agent_ready(pane):
        raise RuntimeError(f"claude did not come up in {pane}")


def submit(pane, text, timeout_s=60):
    """Type `text` into the agent and make sure the turn actually started."""
    r = subprocess.run(["herdr", "agent", "prompt", pane, text, "--wait", "--timeout",
                        str(timeout_s * 1000)], capture_output=True, text=True)
    if r.returncode == 0:
        return True
    err = r.stderr + r.stdout
    if "agent_prompt_stalled" in err or input_line(read_pane(pane)).startswith(text[:20]):
        herdr("agent", "send-keys", pane, "enter", check=False)
        time.sleep(5)
        got = herdr("agent", "get", pane, check=False)
        return (got.get("result") or {}).get("agent", {}).get("agent_status") in ("working", "blocked")
    return "timeout" in err  # still working past the timeout: it did start


def clear_seat(pane):
    """Reset the seat's Claude session: empty input, then /clear.

    /clear starts a new Claude session, and Herdr drops the agent's name with
    the old one -- so the name is put back afterwards.
    """
    name = (herdr("agent", "get", pane, check=False).get("result") or {}).get("agent", {}).get("name")
    herdr("agent", "send-keys", pane, "esc", check=False)
    time.sleep(1)
    if input_line(read_pane(pane)):
        herdr("agent", "send-keys", pane, "ctrl+u", check=False)
        time.sleep(1)
    subprocess.run(["herdr", "agent", "prompt", pane, "/clear"], capture_output=True, text=True)
    time.sleep(4)
    ready = wait_agent_ready(pane, timeout=30)
    if name:
        herdr("agent", "rename", pane, name, check=False)
    return ready


def restart_seat(pane):
    """Restart the seat's Claude: the way out when /clear is not enough.

    A worker that ends with a background task still running (a wait loop for a
    process that never comes back) leaves a seat that is idle but never free,
    and /clear keeps the task. /exit asks what to do with it; "Exit and stop
    tasks" is the dialog's default, so Enter takes it.
    """
    name = (herdr("agent", "get", pane, check=False).get("result") or {}).get("agent", {}).get("name")
    herdr("agent", "send-keys", pane, "esc", check=False)
    time.sleep(1)
    if input_line(read_pane(pane)):
        herdr("agent", "send-keys", pane, "ctrl+u", check=False)
        time.sleep(1)
    subprocess.run(["herdr", "agent", "prompt", pane, "/exit"], capture_output=True, text=True)
    for _ in range(30):
        time.sleep(2)
        agent = (herdr("agent", "get", pane, check=False).get("result") or {}).get("agent")
        if not agent:
            break
        if "Background work" in read_pane(pane):
            herdr("agent", "send-keys", pane, "enter", check=False)
    else:
        raise RuntimeError(f"claude in {pane} did not exit")
    start_claude(pane)
    if name:
        herdr("agent", "rename", pane, name, check=False)


# --- Board / machine -----------------------------------------------------------

def board(*args):
    r = subprocess.run([sys.executable, str(HERE / "board.py"), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"board.py {' '.join(args)}: {r.stderr.strip()}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def comment(number, body):
    c = cfg()
    subprocess.run(["gh", "issue", "comment", str(number), "--repo", c["repo"], "--body", body],
                   capture_output=True, text=True)


def free_ram_gb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024 / 1024
    return 0.0


def cleanup(stage_key, n):
    if stage_key == "plan":
        return
    r = subprocess.run([str(HERE / "cleanup.sh"), stage_key, str(n)], capture_output=True,
                       text=True, timeout=300)
    for line in r.stdout.splitlines():
        log(f"#{n} {stage_key}: {line}", quiet=True)
