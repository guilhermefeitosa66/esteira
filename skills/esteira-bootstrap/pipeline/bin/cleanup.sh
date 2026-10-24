#!/usr/bin/env bash
# Stop everything a job raised, so finished work never keeps holding memory.
#   cleanup.sh <stage> <issue>
# Runs at the end of every dev/review/qa job (worker.py end/human and the
# supervisor call it too, as a safety net), so it must be idempotent and must
# never touch what the maintainer runs: only processes started from this
# issue's worktrees, containers labelled for this issue, and whatever the
# project's own hook (.claude/esteira/hooks/cleanup.sh) knows how to stop.
set -uo pipefail
stage=${1:?stage} issue=${2:?issue}
here=$(cd "$(dirname "$0")" && pwd)
cfg=$here/../config.json
j() { python3 -c "import json,os;c=json.load(open('$cfg'));print(os.path.expanduser($1))"; }
wtdir=$(j "c['worktrees_dir']"); state=$(j "c['state_dir']")
say() { echo "cleanup: $*"; }

# 1. Processes whose working directory is inside one of this issue's worktrees
#    (dev servers, watchers, test runners left behind). Our own ancestors are spared.
spare=" $$ "; p=$$
while [[ $p -gt 1 ]]; do p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' '); [[ -n $p ]] || break; spare+="$p "; done
for wt in "$wtdir"/*-"$issue"; do
  [[ -d $wt ]] || continue
  for pid in $(ls /proc | grep -E '^[0-9]+$'); do
    [[ $spare == *" $pid "* ]] && continue
    cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null) || continue
    if [[ $cwd == "$wt" || $cwd == "$wt/"* ]] && [[ $(stat -c %U "/proc/$pid" 2>/dev/null) == "$USER" ]]; then
      kill "$pid" 2>/dev/null && say "stopped pid $pid ($(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null | cut -c1-60)) in ${wt##*/}"
    fi
  done
done

# 2. Containers started for this issue. Workers label what they start:
#    docker run --label esteira.issue=<N> ...   (compose: labels: esteira.issue: "<N>")
if command -v docker >/dev/null; then
  for c in $(docker ps -q --filter "label=esteira.issue=$issue" 2>/dev/null); do
    docker stop -t 10 "$c" >/dev/null 2>&1 && say "container $c stopped"
  done
fi

# 3. The project's own teardown (emulators, test displays, VMs, daemons...).
hook=$here/../hooks/cleanup.sh
if [[ -x $hook ]]; then
  ESTEIRA_STATE=$state ESTEIRA_WORKTREES=$wtdir timeout 120 "$hook" "$stage" "$issue" 2>&1 | sed 's/^/cleanup (hook): /'
fi
exit 0
