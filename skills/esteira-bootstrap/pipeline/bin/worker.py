#!/usr/bin/env python3
"""Start and finish a pipeline job (the agent sitting in a seat of the stage's Herdr space).

  worker.py begin <stage> <issue>
      Confirms the issue is this stage's to work on, moves it to the stage's
      active column and checks the triage snapshot. Exit 0: go ahead.
      Exit 3: stop now -- the issue was edited after triage (it is sent back
      to triage) or is in a column this stage does not own.

  worker.py end <stage> <issue> [--to "<Status>"]
      Moves the issue on (default: the stage's `next`), drops the claim, tears
      down what the job raised (cleanup.sh) and gives the seat back: the tab is
      labelled `vaga` again. The Claude session stays open; the dispatcher
      /clears it before the next job.
      A QA job sending the issue back to dev is diverted to "Needs maintainer"
      once the issue holds more than `max_qa_failures` FAILED QA reports, so
      dev and QA cannot bounce it back and forth forever.

  worker.py human <stage> <issue> <comment-file>
      Posts the comment, moves the issue to "Needs maintainer" and gives the seat back.
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # noqa: E402


def board(*args):
    try:
        return lib.board(*args)
    except RuntimeError as e:
        sys.exit(str(e))


def drop_claim(stage, n):
    path = lib.state_dir() / "claims.json"
    claims = lib.load(path, {})
    claims.pop(f"{stage}:{n}", None)
    lib.save(path, claims)


def give_seat_back():
    tab = os.environ.get("HERDR_TAB_ID")
    if os.environ.get("HERDR_ENV") == "1" and tab:
        subprocess.run(["herdr", "tab", "rename", tab, lib.SEAT_LABEL], capture_output=True)


def begin(stage_key, n):
    c = lib.cfg()
    stage = c["stages"][stage_key]
    current = board("status", str(n))["status"]
    if current not in (stage["queue"], stage["active"]):
        print(json.dumps({"go": False, "reason": f"issue is in {current!r}, not in {stage['queue']!r}"}))
        sys.exit(3)
    snap = board("snapshot", "check", str(n))
    if not snap["ok"]:
        subprocess.run(["gh", "issue", "edit", str(n), "--repo", c["repo"], "--remove-label", "triaged"],
                       capture_output=True)
        board("clear", str(n))
        drop_claim(stage_key, n)
        lib.wake(stage_key)
        print(json.dumps({"go": False, "reason": snap["reason"] + "; sent back to triage"}))
        sys.exit(3)
    if current != stage["active"]:
        board("move", str(n), stage["active"])
    print(json.dumps({"go": True, "issue": n, "stage": stage_key, "next": stage["next"],
                      "repo": c["repo"], "base_branch": c.get("base_branch", "main")}))


QA_FAILED_RE = re.compile(r"^## QA report\b.*\bFAILED\b", re.M)


def qa_failures(c, n):
    """FAILED QA reports on the issue, counting only the pipeline's own comments
    (written by a maintainer or by the account the pipeline runs as)."""
    me = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True).stdout.strip()
    trusted = set(c.get("maintainers", [])) | ({me} if me else set())
    out = subprocess.run(["gh", "issue", "view", str(n), "--repo", c["repo"], "--json", "comments",
                          "--jq", ".comments[] | {author: .author.login, body: .body}"],
                         capture_output=True, text=True, check=True).stdout
    count = 0
    for line in out.splitlines():
        cm = json.loads(line)
        if (cm["author"] in trusted and "<!-- pipeline:qa -->" in cm["body"]
                and QA_FAILED_RE.search(cm["body"])):
            count += 1
    return count


def qa_loop_guard(c, stage_key, n, to):
    """Divert a QA rejection past the limit to Needs maintainer. Returns the destination."""
    limit = c.get("max_qa_failures")
    if stage_key != "qa" or not limit or to != c["stages"]["dev"]["queue"]:
        return to
    failures = qa_failures(c, n)
    if failures <= limit:
        return to
    subprocess.run(["gh", "issue", "comment", str(n), "--repo", c["repo"], "--body",
                    f"<!-- pipeline:human -->\nQA has now failed this issue {failures} times "
                    f"(limit: {limit} returns to development). Instead of another round, it goes "
                    "to **Needs maintainer**: the QA reports above hold the history of what kept "
                    "failing."], capture_output=True)
    lib.log(f"#{n} qa: {failures} FAILED rounds > {limit} -> Needs maintainer")
    return "Needs maintainer"


def end(stage_key, n, to=None):
    c = lib.cfg()
    stage = c["stages"][stage_key]
    to = qa_loop_guard(c, stage_key, n, to)
    board("move", str(n), to or stage["next"])
    drop_claim(stage_key, n)
    try:
        lib.cleanup(stage_key, n)
    except Exception as e:  # a stuck teardown must not keep the issue claimed
        print(f"cleanup failed: {e}", file=sys.stderr)
    give_seat_back()
    # This stage has a free seat; the stage after it may have a new item.
    lib.wake(stage_key, lib.stage_for_queue(c, to or stage["next"]))
    lib.log(f"#{n} {stage_key}: done -> {to or stage['next']}", quiet=True)
    print(json.dumps({"issue": n, "moved_to": to or stage["next"], "seat": "released"}))


def human(stage_key, n, comment_file):
    c = lib.cfg()
    subprocess.run(["gh", "issue", "comment", str(n), "--repo", c["repo"], "--body-file", comment_file],
                   check=True, capture_output=True)
    end(stage_key, n, "Needs maintainer")


def main(argv):
    if len(argv) < 3:
        sys.exit(__doc__)
    cmd, stage, n = argv[0], argv[1], int(argv[2])
    if stage not in lib.cfg()["stages"]:
        sys.exit(f"unknown stage {stage}")
    if cmd == "begin":
        begin(stage, n)
    elif cmd == "end":
        to = argv[argv.index("--to") + 1] if "--to" in argv else None
        end(stage, n, to)
    elif cmd == "human":
        human(stage, n, argv[3])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
