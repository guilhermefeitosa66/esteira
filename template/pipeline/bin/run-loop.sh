#!/usr/bin/env bash
# Run a monitoring skill forever, each tick in a FRESH Claude session, so the
# context never grows and never degrades.
#   run-loop.sh <skill> <seconds>      e.g. run-loop.sh esteira-triagem 3600
set -uo pipefail
skill=$1 every=$2
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../../.." && pwd)
j() { python3 -c "import json,os;c=json.load(open('$here/../config.json'));print(os.path.expanduser($1))"; }
state=$(j "c['state_dir']")
claude=$(j "c.get('claude_command','claude --dangerously-skip-permissions')")
mkdir -p "$state/logs"; cd "$repo"
while true; do
  echo "=== $(date '+%F %T') /$skill" >> "$state/logs/$skill.log"
  timeout 3000 $claude -p "/$skill" >> "$state/logs/$skill.log" 2>&1
  tail -n 3 "$state/logs/$skill.log"
  sleep "$every"
done
