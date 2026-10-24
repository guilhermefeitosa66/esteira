#!/usr/bin/env python3
"""Queue dispatcher: hands queued issues to the stage's fixed seats in Herdr.

  dispatch.py <stage>            one pass (plan | dev | review | qa)
  dispatch.py <stage> --loop N   one pass every N seconds, forever (no LLM tokens)
  dispatch.py seats <stage>      make sure the stage's seats exist (tabs 2..max+1, Claude open)

One pass, under the machine-wide pipeline lock:

  1. reconcile: a claim whose issue already left the active column is dropped;
     an issue in the active column with no claim goes back to its queue.
     (Seats that are alive but stuck are the supervisor's job, see supervise.py.)
  2. memory budget: a heavy stage (dev/review/qa) dispatches nothing while
     MemAvailable is below `min_free_ram_gb`.
  3. for each queued issue while a seat is free: check the triage snapshot,
     claim it (move to the active column), /clear the seat, rename the tab
     `#N stage`, prompt `/<skill> N` and confirm the turn started.

The space is the one named in `stages.<stage>.space`, wherever this runs.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def seat_name(stage_key, k):
    return lib.seat_name(stage_key, k)


def ensure_seats(stage_key, c):
    """Tabs 2..max+1 of the stage's space, each with a named Claude. Returns free/busy seats."""
    stage = c["stages"][stage_key]
    ws, seats = lib.seats(stage_key, c)
    if not ws:
        lib.log(f"{stage_key}: no Herdr space named {stage['space']!r}; nothing to do")
        return []
    claims = lib.load(lib.state_dir() / "claims.json", {})
    busy_panes = {cl.get("pane") for cl in claims.values() if cl["stage"] == stage_key}
    used = {s["agent"].get("name") for s in seats if s["agent"]}
    # Name any unnamed Claude sitting in a seat (after a restart the names are gone).
    for s in seats:
        a = s["agent"]
        if a and not a.get("name") and s["pane"] not in busy_panes:
            k = next(k for k in range(1, 99) if seat_name(stage_key, k) not in used)
            lib.herdr("agent", "rename", s["pane"], seat_name(stage_key, k), check=False)
            used.add(seat_name(stage_key, k))
            a["name"] = seat_name(stage_key, k)
    # Open missing seats up to `max`.
    while len(seats) < stage["max"]:
        res = lib.herdr("tab", "create", "--workspace", ws, "--cwd", str(lib.REPO_DIR),
                        "--label", lib.SEAT_LABEL, "--no-focus")["result"]
        pane = res["root_pane"]["pane_id"]
        lib.start_claude(pane)
        k = next(k for k in range(1, 99) if seat_name(stage_key, k) not in used)
        lib.herdr("agent", "rename", pane, seat_name(stage_key, k))
        used.add(seat_name(stage_key, k))
        lib.log(f"{stage_key}: opened seat {seat_name(stage_key, k)} in {res['tab']['tab_id']}")
        ws, seats = lib.seats(stage_key, c)
    # A seat whose Claude is gone (shell at the prompt) gets one back.
    for s in seats:
        if not s["agent"] and s["pane"] not in busy_panes and "@" in s["title"]:
            lib.start_claude(s["pane"])
            k = next(k for k in range(1, 99) if seat_name(stage_key, k) not in used)
            lib.herdr("agent", "rename", s["pane"], seat_name(stage_key, k), check=False)
            used.add(seat_name(stage_key, k))
            lib.log(f"{stage_key}: restarted Claude in seat {s['tab']} as {seat_name(stage_key, k)}")
    return lib.seats(stage_key, c)[1]


def reconcile(stage_key, c):
    stage = c["stages"][stage_key]
    path = lib.state_dir() / "claims.json"
    claims = lib.load(path, {})
    for key, cl in list(claims.items()):
        if cl["stage"] != stage_key:
            continue
        status = lib.board("status", str(cl["issue"]))["status"]
        if status != stage["active"]:
            del claims[key]  # the worker moved it on; only the claim was left behind
            lib.log(f"#{cl['issue']} {stage_key}: claim dropped (issue is in {status!r})")
    lib.save(path, claims)
    claimed = {cl["issue"] for cl in claims.values() if cl["stage"] == stage_key}
    for item in lib.board("list", stage["active"]) or []:
        if item["number"] not in claimed:
            lib.board("move", str(item["number"]), stage["queue"])
            lib.log(f"#{item['number']} {stage_key}: in {stage['active']!r} with no worker -> back to queue")
    return claims


def free_seats(stage_key, seats, claims):
    busy = {cl.get("pane") for cl in claims.values() if cl["stage"] == stage_key}
    out = []
    for s in seats:
        a = s["agent"]
        if not a or s["pane"] in busy or a.get("agent_status") not in ("idle", "done"):
            continue
        if lib.background_tasks(lib.read_pane(s["pane"])):
            continue  # something from the last job is still running; the supervisor handles it
        out.append(s)
    return out


def dispatch_one(stage_key, n, seat, c, claims):
    stage = c["stages"][stage_key]
    key = f"{stage_key}:{n}"
    attempts = lib.load(lib.state_dir() / "attempts.json", {}).get(key, 0)
    lib.board("move", str(n), stage["active"])
    claims[key] = {"stage": stage_key, "issue": n, "agent": seat["agent"]["name"], "pane": seat["pane"],
                   "tab": seat["tab"], "ts": time.time(), "seen": time.time(), "attempts": attempts,
                   "prompt": f"/{stage['skill']} {n}"}
    lib.save(lib.state_dir() / "claims.json", claims)
    if not lib.clear_seat(seat["pane"]):
        raise RuntimeError(f"seat {seat['pane']} did not come back after /clear")
    lib.herdr("tab", "rename", seat["tab"], f"#{n} {stage_key}", check=False)
    if not lib.submit(seat["pane"], f"/{stage['skill']} {n}", c["timeouts"]["prompt_start_seconds"]):
        raise RuntimeError("prompt did not start a turn")
    claims[key]["started"] = time.time()
    lib.save(lib.state_dir() / "claims.json", claims)
    lib.log(f"#{n} {stage_key}: dispatched to {seat['agent']['name']} ({seat['tab']})")


def one_pass(stage_key):
    lib.require_herdr()
    try:
        c = lib.cfg()
    except lib.ConfigError as e:
        lib.log(f"{stage_key}: pass skipped: {e}")
        return
    stage = c["stages"][stage_key]
    with lib.pipeline_lock():
        claims = reconcile(stage_key, c)
        queued = lib.board("list", stage["queue"]) or []
        seats = ensure_seats(stage_key, c)
        if not queued:
            return
        if stage.get("heavy") and lib.free_ram_gb() < c["min_free_ram_gb"]:
            lib.log(f"{stage_key}: {len(queued)} queued, paused: low memory "
                    f"({lib.free_ram_gb():.1f} GB free < {c['min_free_ram_gb']} GB)")
            return
        busy = sum(1 for cl in claims.values() if cl["stage"] == stage_key)
        free = free_seats(stage_key, seats, claims)
        room = min(len(free), stage["max"] - busy, c["max_workers"] - len(claims))
        if room <= 0:
            why = (f"{busy} of {stage['max']} seats busy" if busy >= stage["max"] else
                   "pipeline-wide cap reached" if len(claims) >= c["max_workers"] else "seat not ready")
            lib.log(f"{stage_key}: {len(queued)} queued, waiting ({why})")
            return
        for item, seat in zip(queued[:room], free):
            n = item["number"]
            snap = lib.board("snapshot", "check", str(n))
            if not snap["ok"]:
                subprocess.run(["gh", "issue", "edit", str(n), "--repo", c["repo"],
                                "--remove-label", "triaged"], capture_output=True)
                lib.board("clear", str(n))
                lib.log(f"#{n} {stage_key}: {snap['reason']} -> back to triage")
                continue
            try:
                dispatch_one(stage_key, n, seat, c, claims)
            except Exception as e:  # claim stays; the supervisor nudges or recycles it
                lib.log(f"#{n} {stage_key}: dispatch problem: {e}")


def main(argv):
    if not argv:
        sys.exit(__doc__)
    if argv[0] == "seats":
        lib.require_herdr()
        with lib.pipeline_lock():
            for s in ensure_seats(argv[1], lib.cfg()):
                print(s["tab"], s["label"], (s["agent"] or {}).get("name"))
        return
    stage_key = argv[0]
    if stage_key not in lib.cfg()["stages"]:
        sys.exit(f"unknown stage {stage_key}")
    if "--loop" in argv:
        every = int(argv[argv.index("--loop") + 1])
        while True:
            try:
                one_pass(stage_key)
            except Exception as e:
                lib.log(f"{stage_key}: pass failed: {e}")
            time.sleep(every)
    one_pass(stage_key)


if __name__ == "__main__":
    main(sys.argv[1:])
