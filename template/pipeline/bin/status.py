#!/usr/bin/env python3
"""One screen with the whole pipeline: queues, seats, locks, memory, loops.

  status.py            text table
  status.py --json     the same as JSON
"""
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def ago(ts):
    if not ts:
        return "-"
    m = int((time.time() - ts) / 60)
    return f"{m} min" if m < 120 else f"{m // 60} h"


def locks():
    """Every machine-wide lock taken through lock.sh: name -> who holds it."""
    return {p.stem: lock_owner(p.stem) for p in sorted(lib.state_dir().glob("*.owner"))}


def lock_owner(name):
    p = lib.state_dir() / f"{name}.owner"
    o = lib.load(p, None)
    if not o:
        return "livre"
    alive = os.path.exists(f"/proc/{o['pid']}")
    return f"{'em uso' if alive else 'dono morto'} há {ago(o['since'])} ({os.path.basename(o['cwd'])})"


def loops():
    out = {}
    ps = subprocess.run(["ps", "-eo", "args"], capture_output=True, text=True).stdout
    b = str(lib.HERE)  # full path: another project's loops on the same machine must not count
    needles = [(f"dispatch {k}", f"{b}/dispatch.py {k} --loop") for k in lib.cfg()["stages"]]
    needles.append(("supervisor", f"{b}/supervise.py --loop"))
    if lib.cfg().get("monitors"):
        needles += [("triagem", f"{b}/run-loop.sh esteira-triagem"), ("monitor-prs", f"{b}/run-loop.sh esteira-monitor-prs")]
    for name, needle in needles:
        out[name] = needle in ps
    return out


def main():
    c = lib.cfg()
    claims = lib.load(lib.state_dir() / "claims.json", {})
    data = {"ram_free_gb": round(lib.free_ram_gb(), 1), "min_free_ram_gb": c["min_free_ram_gb"],
            "locks": locks(), "loops": loops(), "stages": {}}
    for key, st in c["stages"].items():
        queued = [i["number"] for i in (lib.board("list", st["queue"]) or [])]
        seats = []
        if os.environ.get("HERDR_ENV") == "1":
            _, ss = lib.seats(key, c)
            for s in ss:
                cl = next((x for x in claims.values() if x.get("pane") == s["pane"]), None)
                a = s["agent"] or {}
                seats.append({"tab": s["tab"], "label": s["label"], "agent": a.get("name"),
                              "status": a.get("agent_status") or "sem Claude",
                              "issue": cl["issue"] if cl else None, "since": ago(cl["ts"]) if cl else "-"})
        data["stages"][key] = {"queue": queued, "seats": seats, "max": st["max"]}
    if "--json" in sys.argv:
        print(json.dumps(data, indent=1, ensure_ascii=False))
        return
    locks = ", ".join(f"{k}: {v}" for k, v in data["locks"].items()) or "nenhuma"
    print(f"RAM livre: {data['ram_free_gb']} GB (pausa abaixo de {c['min_free_ram_gb']} GB) · travas: {locks}")
    print("Loops: " + ", ".join(f"{k} {'✓' if v else '✗'}" for k, v in data["loops"].items()))
    for key, s in data["stages"].items():
        print(f"\n[{key}] fila ({len(s['queue'])}): {' '.join('#%d' % n for n in s['queue']) or '-'}")
        for seat in s["seats"] or [{"tab": "-", "label": "sem vagas", "agent": "", "status": "", "issue": None, "since": "-"}]:
            job = f"#{seat['issue']} há {seat['since']}" if seat["issue"] else "livre"
            print(f"  {seat['tab']:<8} {seat['label']:<14} {seat['agent'] or '':<14} {seat['status']:<11} {job}")


if __name__ == "__main__":
    main()
