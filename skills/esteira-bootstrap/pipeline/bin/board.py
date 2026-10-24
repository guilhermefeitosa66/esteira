#!/usr/bin/env python3
"""Board and issue helpers shared by the esteira skills.

Every subcommand prints JSON (or nothing) and exits non-zero on error, so the
skills read results instead of guessing. Talks to GitHub only through `gh`.

  board.py list "<Status>"            items in a column, oldest issue first
  board.py status <issue>             current column of an issue ("" if none)
  board.py move <issue> "<Status>"    move (adds the issue to the board if needed)
  board.py clear <issue>              remove the Status (sends it back to triage)
  board.py snapshot save <issue>      record the title+body hash seen at triage
  board.py snapshot check <issue>     {"ok": bool, ...}: body unchanged since triage?
  board.py pr-for <issue>             the open PR that belongs to the issue, if any
  board.py map-pr <issue> <pr> <sha>  tie an approved external PR (at that head) to its issue
  board.py move-url <url> "<Status>"  put a PR on the board in a column
  board.py untriaged                  open issues that still need triage
"""
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
CFG = json.loads((HERE.parent / "config.json").read_text())
STATE = Path(os.path.expanduser(CFG["state_dir"]))
STATE.mkdir(parents=True, exist_ok=True)
REPO = CFG["repo"]
OWNER, NAME = REPO.split("/")


def gh(*args, check=True):
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])}: {r.stderr.strip()}")
    return r.stdout


def graphql(query, **variables):
    args = ["api", "graphql", "-f", f"query={query}"]
    for k, v in variables.items():
        args += ["-F" if isinstance(v, int) else "-f", f"{k}={v}"]
    return json.loads(gh(*args))["data"]


ITEMS_Q = """
query($owner:String!,$number:Int!,$cursor:String){
  owner: OWNER_KIND(login:$owner){ projectV2(number:$number){
    items(first:100, after:$cursor){
      pageInfo{ hasNextPage endCursor }
      nodes{ id
        status: fieldValueByName(name:"STATUS_FIELD"){ ... on ProjectV2ItemFieldSingleSelectValue{ name updatedAt } }
        priority: fieldValueByName(name:"Priority"){ ... on ProjectV2ItemFieldSingleSelectValue{ name } }
        content{ ... on Issue{ number title state url author{login} repository{nameWithOwner} } }
      }
    }
  }}
}"""


def all_items():
    cursor, out = None, []
    while True:
        v = {"owner": CFG["owner"], "number": CFG["project_number"]}
        if cursor:
            v["cursor"] = cursor
        page = graphql(ITEMS_Q.replace("OWNER_KIND", CFG.get("owner_type", "user")).replace("STATUS_FIELD", CFG.get("status_field_name", "Status")), **v)["owner"]["projectV2"]["items"]
        for n in page["nodes"]:
            c = n.get("content") or {}
            if c.get("repository", {}).get("nameWithOwner") != REPO:
                continue
            out.append({
                "item_id": n["id"],
                "number": c["number"],
                "title": c["title"],
                "state": c["state"],
                "author": (c.get("author") or {}).get("login"),
                "status": (n.get("status") or {}).get("name") or "",
                "status_updated": (n.get("status") or {}).get("updatedAt"),
                "priority": (n.get("priority") or {}).get("name") or "",
            })
        if not page["pageInfo"]["hasNextPage"]:
            return out
        cursor = page["pageInfo"]["endCursor"]


def item_for(number):
    for it in all_items():
        if it["number"] == number:
            return it
    return None


def ensure_item(number):
    it = item_for(number)
    if it:
        return it["item_id"]
    url = f"https://github.com/{REPO}/issues/{number}"
    out = gh("project", "item-add", str(CFG["project_number"]), "--owner", CFG["owner"],
             "--url", url, "--format", "json")
    return json.loads(out)["id"]


def move(number, status):
    if status not in CFG["status_options"]:
        sys.exit(f"unknown status {status!r}; valid: {list(CFG['status_options'])}")
    item = ensure_item(number)
    gh("project", "item-edit", "--project-id", CFG["project_id"], "--id", item,
       "--field-id", CFG["status_field_id"],
       "--single-select-option-id", CFG["status_options"][status])
    print(json.dumps({"issue": number, "status": status}))


def clear(number):
    it = item_for(number)
    if it:
        gh("project", "item-edit", "--project-id", CFG["project_id"], "--id", it["item_id"],
           "--field-id", CFG["status_field_id"], "--clear")
    print(json.dumps({"issue": number, "status": ""}))


def issue(number):
    return json.loads(gh("issue", "view", str(number), "--repo", REPO, "--json",
                         "number,title,body,author,state,labels,updatedAt"))


def digest(i):
    return hashlib.sha256((i["title"] + "\n\0\n" + (i["body"] or "")).encode()).hexdigest()


SNAP = STATE / "snapshots.json"


def snapshots():
    return json.loads(SNAP.read_text()) if SNAP.exists() else {}


def snapshot(cmd, number):
    i = issue(number)
    snaps = snapshots()
    if cmd == "save":
        snaps[str(number)] = {"sha256": digest(i), "saved": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        SNAP.write_text(json.dumps(snaps, indent=1))
        print(json.dumps({"issue": number, "saved": True}))
        return
    rec = snaps.get(str(number))
    if rec is None:
        print(json.dumps({"issue": number, "ok": False, "reason": "no triage snapshot"}))
    elif rec["sha256"] != digest(i):
        print(json.dumps({"issue": number, "ok": False, "reason": "title or body edited after triage"}))
    else:
        print(json.dumps({"issue": number, "ok": True}))


PRMAP = STATE / "prmap.json"


def pr_for(number):
    # External PRs the PR monitor approved are mapped explicitly.
    mapped = json.loads(PRMAP.read_text()).get(str(number)) if PRMAP.exists() else None
    if mapped:
        p = json.loads(gh("pr", "view", str(mapped["pr"]), "--repo", REPO, "--json",
                          "number,title,headRefName,headRefOid,author,body,url,"
                          "isCrossRepository,maintainerCanModify,state"))
        p["approved_sha"] = mapped["sha"]
        print(json.dumps(p))
        return
    prs = json.loads(gh("pr", "list", "--repo", REPO, "--state", "open", "--limit", "100",
                        "--json", "number,title,headRefName,headRefOid,author,body,url,isCrossRepository"))
    # Pipeline branches are named <type>/issue-<N>-<slug>; the trailing "-"
    # keeps issue-5 from matching issue-50.
    tag = f"issue-{number}-"
    for p in prs:
        if tag in p["headRefName"] + "-":
            print(json.dumps(p))
            return
    # External PRs: whatever the branch is called, they name the issue.
    for p in prs:
        body = p.get("body") or ""
        if f"Part of #{number}" in body or f"[issue-{number}]" in p["title"]:
            print(json.dumps(p))
            return
    print("null")


def map_pr(number, pr, sha):
    data = json.loads(PRMAP.read_text()) if PRMAP.exists() else {}
    data[str(number)] = {"pr": pr, "sha": sha}
    PRMAP.write_text(json.dumps(data, indent=1))
    print(json.dumps({"issue": number, "pr": pr, "sha": sha}))


def move_url(url, status):
    """Put a pull request (or any URL) on the board, e.g. a PR that needs the maintainer."""
    out = gh("project", "item-add", str(CFG["project_number"]), "--owner", CFG["owner"],
             "--url", url, "--format", "json")
    gh("project", "item-edit", "--project-id", CFG["project_id"], "--id", json.loads(out)["id"],
       "--field-id", CFG["status_field_id"],
       "--single-select-option-id", CFG["status_options"][status])
    print(json.dumps({"url": url, "status": status}))


def untriaged():
    raw = json.loads(gh("issue", "list", "--repo", REPO, "--state", "open", "--limit", "200",
                        "--json", "number,title,author,labels,createdAt"))
    skip = {"triaged"} | ({CFG["quarantine"]["label"]} if CFG.get("quarantine") else set())
    out = [{"number": i["number"], "title": i["title"], "author": i["author"]["login"],
            "created": i["createdAt"]}
           for i in raw if not skip & {l["name"] for l in i["labels"]}]
    print(json.dumps(sorted(out, key=lambda x: x["number"])))


PRIO = {"P0": 0, "P1": 1, "P2": 2, "": 3}


def main(argv):
    if not argv:
        sys.exit(__doc__)
    cmd, rest = argv[0], argv[1:]
    if cmd == "list":
        items = [i for i in all_items() if i["status"] == rest[0] and i["state"] == "OPEN"]
        items.sort(key=lambda i: (PRIO.get(i["priority"], 3), i["number"]))
        print(json.dumps(items))
    elif cmd == "status":
        it = item_for(int(rest[0]))
        print(json.dumps({"issue": int(rest[0]), "status": it["status"] if it else ""}))
    elif cmd == "move":
        move(int(rest[0]), rest[1])
    elif cmd == "clear":
        clear(int(rest[0]))
    elif cmd == "snapshot":
        snapshot(rest[0], int(rest[1]))
    elif cmd == "pr-for":
        pr_for(int(rest[0]))
    elif cmd == "map-pr":
        map_pr(int(rest[0]), int(rest[1]), rest[2])
    elif cmd == "move-url":
        move_url(rest[0], rest[1])
    elif cmd == "untriaged":
        untriaged()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
