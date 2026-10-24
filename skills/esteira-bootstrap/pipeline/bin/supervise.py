#!/usr/bin/env python3
"""Pipeline supervisor: finds seats that are alive but stuck, and unsticks them.

  supervise.py             one pass
  supervise.py --loop N    one pass every N seconds, forever (no LLM tokens)
  supervise.py --dry       one pass that only reports what it would do

The dispatcher only knows "the worker is gone". Every real stall so far was the
opposite -- the Claude in the seat still alive and doing nothing -- so this
crosses Herdr's agents with the claims and the board, every pass:

  claimed seat, Claude lost its name (restart)  -> rename it back
  claimed seat, Claude gone                     -> recycle (issue back to its queue)
  prompt typed but never submitted              -> Enter; twice without luck -> recycle
  blocked on a dialog > blocked_minutes         -> Esc, comment, Needs maintainer
  idle > idle_nudge_minutes, nothing running    -> one nudge: finish with worker.py end/human
  still idle idle_give_up_minutes after nudge   -> recycle
  idle with background work for 3x the nudge    -> treated as idle (nudge, then recycle)
  tab says "#N stage" but nobody claims it      -> duplicate: /clear it; orphan: adopt or free
  more seats than `max`, idle and clean         -> close the extras

Recycle = cleanup.sh, attempts+1 (Needs maintainer after max_attempts), /clear
the seat, label it `vaga`, drop the claim. Every action goes to dispatch.log.
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402

DRY = "--dry" in sys.argv
TAB_RE = re.compile(r"^#(\d+) (\w+)$")


def act(msg):
    lib.log(("[dry] " if DRY else "") + "supervisor: " + msg)
    return not DRY


def recycle(c, claims, key, why, commented=False):
    cl = claims[key]
    stage_key, n = cl["stage"], cl["issue"]
    stage = c["stages"][stage_key]
    attempts = cl.get("attempts", 0) + 1
    if not act(f"#{n} {stage_key}: {why} -> recycling (attempt {attempts})"):
        return
    try:
        lib.cleanup(stage_key, n)
    except Exception as e:
        lib.log(f"#{n} {stage_key}: cleanup failed: {e}")
    if attempts >= c["max_attempts"]:
        lib.board("move", str(n), "Needs maintainer")
        if not commented:
                lib.comment(n, f"<!-- pipeline:supervisor -->\nPipeline: the `{stage_key}` stage stalled "
                           f"{attempts} times without finishing (last: {why}). Moved to **Needs maintainer**.")
    else:
        lib.board("move", str(n), stage["queue"])
        retries = lib.load(lib.state_dir() / "attempts.json", {})
        retries[key] = attempts
        lib.save(lib.state_dir() / "attempts.json", retries)
    pane = cl.get("pane")
    if pane and lib.herdr("agent", "get", pane, check=False).get("result"):
        lib.clear_seat(pane)
    if cl.get("tab"):
        lib.herdr("tab", "rename", cl["tab"], lib.SEAT_LABEL, check=False)
    del claims[key]


def supervise_claim(c, claims, key, seat_by_pane, track, now):
    cl = claims[key]
    stage_key, n = cl["stage"], cl["issue"]
    t = c["timeouts"]
    tr = track.setdefault(key, {})
    # Legacy claims (before seats) only carry the agent name.
    if not cl.get("pane"):
        for s in seat_by_pane.values():
            if s["agent"] and s["agent"].get("name") == cl["agent"]:
                cl["pane"], cl["tab"] = s["pane"], s["tab"]
    seat = seat_by_pane.get(cl.get("pane"))
    if not seat or not seat["agent"]:
        gone = now - cl.get("seen", cl["ts"])
        if gone > c["stale_minutes"] * 60:
            recycle(c, claims, key, f"no Claude in the seat for {gone / 60:.0f} min")
        return
    a = seat["agent"]
    if a.get("name") != cl["agent"]:
        if act(f"#{n} {stage_key}: renaming {seat['pane']} back to {cl['agent']}"):
            lib.herdr("agent", "rename", seat["pane"], cl["agent"], check=False)
    cl["seen"] = now
    st = a.get("agent_status")
    if st == "working":
        track[key] = {}
        return  # nothing to do, and no GitHub call: the board is only asked about seats that look stuck
    status = lib.board("status", str(n))["status"]
    if status != c["stages"][stage_key]["active"]:
        return  # finished; the dispatcher drops the claim, the seat frees itself
    screen = lib.read_pane(seat["pane"])
    if st == "blocked":
        tr.setdefault("blocked_since", now)
        if now - tr["blocked_since"] > t["blocked_minutes"] * 60:
            tail = "\n".join(l for l in screen.splitlines() if l.strip())[-1200:]
            if act(f"#{n} {stage_key}: blocked on a dialog for {t['blocked_minutes']} min -> Needs maintainer"):
                lib.herdr("agent", "send-keys", seat["pane"], "esc", check=False)
                lib.comment(n, "<!-- pipeline:supervisor -->\nPipeline: the worker stopped on a dialog it "
                               "could not answer. Moved to **Needs maintainer**. Last screen:\n\n```\n"
                               + tail + "\n```")
                cl["attempts"] = c["max_attempts"]
                recycle(c, claims, key, "blocked on a dialog", commented=True)
        return
    tr.pop("blocked_since", None)
    # idle / done / unknown from here on
    typed = lib.input_line(screen)
    if cl.get("prompt") and typed.startswith(cl["prompt"]):
        tr["enters"] = tr.get("enters", 0) + 1
        if tr["enters"] > 2:
            recycle(c, claims, key, "prompt never submitted")
        elif act(f"#{n} {stage_key}: prompt typed but not submitted -> Enter"):
            lib.herdr("agent", "send-keys", seat["pane"], "enter", check=False)
        return
    bg = lib.background_tasks(screen)
    tr.setdefault("idle_since", now)
    idle = (now - tr["idle_since"]) / 60
    limit = t["idle_nudge_minutes"] * (3 if bg else 1)
    if not tr.get("nudged"):
        if idle > limit and act(f"#{n} {stage_key}: idle {idle:.0f} min (background tasks: {bg}) -> nudge"):
            lib.herdr("agent", "send-keys", seat["pane"], "esc", check=False)
            time.sleep(1)
            lib.submit(seat["pane"],
                       f"Pipeline supervisor: issue #{n} is still in the {stage_key} stage and this seat has "
                       f"been idle for {idle:.0f} min. Finish the job now, following the skill: stop your "
                       f"background tasks, run cleanup, and call worker.py end {stage_key} {n} (or worker.py "
                       f"human if you are blocked on a decision only the maintainer can make).", 30)
            tr["nudged"] = now
        return
    if (now - tr["nudged"]) / 60 > t["idle_give_up_minutes"]:
        recycle(c, claims, key, f"idle after a nudge ({idle:.0f} min in total)")


def supervise_unclaimed(c, stage_key, seats, claims, track):
    stage = c["stages"][stage_key]
    claimed_panes = {cl.get("pane") for cl in claims.values()}
    by_issue = {(cl["stage"], cl["issue"]): cl for cl in claims.values()}
    canonical = [lib.seat_name(stage_key, k, c) for k in range(1, stage["max"] + 1)]
    names = {(s["agent"] or {}).get("name") for s in seats}
    idle_clean = []
    for s in seats:
        if s["pane"] in claimed_panes:
            continue
        a = s["agent"]
        m = TAB_RE.match(s["label"])
        if m and m.group(2) == stage_key:
            n = int(m.group(1))
            owner = by_issue.get((stage_key, n))
            if owner and owner.get("pane") != s["pane"]:
                if act(f"#{n} {stage_key}: duplicate worker in {s['tab']} -> /clear"):
                    lib.clear_seat(s["pane"])
                    lib.herdr("tab", "rename", s["tab"], lib.SEAT_LABEL, check=False)
                continue
            if (a and a.get("agent_status") == "working"
                    and lib.board("status", str(n))["status"] == stage["active"]):
                if act(f"#{n} {stage_key}: unclaimed worker in {s['tab']} -> adopting it"):
                    key = f"{stage_key}:{n}"
                    claims[key] = {"stage": stage_key, "issue": n, "agent": a.get("name") or lib.seat_name(stage_key, n, c),
                                   "pane": s["pane"], "tab": s["tab"], "ts": time.time(), "seen": time.time(),
                                   "attempts": 0, "prompt": f"/{stage['skill']} {n}"}
                continue
            if a and a.get("agent_status") in ("idle", "done") and act(f"{s['tab']}: job #{n} over -> seat is free"):
                lib.herdr("tab", "rename", s["tab"], lib.SEAT_LABEL, check=False)
        if a and a.get("agent_status") in ("idle", "done"):
            leftover = f"leftover:{s['pane']}"
            if not lib.background_tasks(lib.read_pane(s["pane"])):
                track.pop(leftover, None)
                idle_clean.append(s)
            elif time.time() - track.setdefault(leftover, time.time()) > c["timeouts"]["leftover_task_minutes"] * 60:
                # no job, yet a background task holds the seat: a worker left it behind
                if act(f"{s['tab']}: background task left running with no job -> restarting the seat's Claude"):
                    lib.restart_seat(s["pane"])
                    lib.herdr("tab", "rename", s["tab"], lib.SEAT_LABEL, check=False)
                    track.pop(leftover, None)
    # Normalize names and trim seats beyond `max`.
    free_names = [x for x in canonical if x not in names]
    keep = sum(1 for s in seats if s["pane"] in claimed_panes)
    for s in idle_clean:
        name = s["agent"].get("name")
        if keep < stage["max"]:
            keep += 1
            if name not in canonical and free_names and act(f"{s['tab']}: seat renamed {name} -> {free_names[0]}"):
                lib.herdr("agent", "rename", s["pane"], free_names.pop(0), check=False)
        elif act(f"{stage_key}: extra seat {s['tab']} ({name}) -> closing"):
            lib.herdr("tab", "close", s["tab"], check=False)


def one_pass():
    lib.require_herdr()
    try:
        c = lib.cfg()
    except lib.ConfigError as e:
        lib.log(f"supervisor: pass skipped: {e}")
        return
    with lib.pipeline_lock():
        claims_path = lib.state_dir() / "claims.json"
        track_path = lib.state_dir() / "supervise.json"
        claims = lib.load(claims_path, {})
        track = lib.load(track_path, {})
        now = time.time()
        for stage_key in c["stages"]:
            _, seats = lib.seats(stage_key, c)
            seat_by_pane = {s["pane"]: s for s in seats}
            for key in [k for k, cl in claims.items() if cl["stage"] == stage_key]:
                try:
                    supervise_claim(c, claims, key, seat_by_pane, track, now)
                except Exception as e:
                    lib.log(f"supervisor: {key}: {e}")
            try:
                supervise_unclaimed(c, stage_key, lib.seats(stage_key, c)[1], claims, track)
            except Exception as e:
                lib.log(f"supervisor: {stage_key} seats: {e}")
        for key in list(track):
            if key not in claims and not key.startswith("leftover:"):
                del track[key]
        if not DRY:
            lib.save(claims_path, claims)
            lib.save(track_path, track)
        if lib.free_ram_gb() < c["min_free_ram_gb"] / 2:
            lib.log(f"supervisor: memory is low ({lib.free_ram_gb():.1f} GB free); heavy stages are paused")


def main(argv):
    if "--loop" in argv:
        every = int(argv[argv.index("--loop") + 1])
        while True:
            try:
                one_pass()
            except Exception as e:
                lib.log(f"supervisor: pass failed: {e}")
            time.sleep(every)
    one_pass()


if __name__ == "__main__":
    main(sys.argv[1:])
