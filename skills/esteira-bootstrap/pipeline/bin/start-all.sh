#!/usr/bin/env bash
# Provision the whole pipeline in Herdr -- from nothing, or back up after a
# reboot -- without duplicating anything that is already running.
#   start-all.sh          adopt/create the spaces, start what is missing
#   start-all.sh --dry    print what it would do
#
# Layout (one Herdr space each, names from config.json, created if missing):
#   product                       (product_space) first, no loop: where the maintainer
#       does discovery, writes issues and follows the pipeline
#   plan / dev / review / qa      (stages.<x>.space)
#       tab 1 "monitor": dispatch.py <stage> --loop      tabs 2..: seats (Claude kept open)
#   homolog / release             (manual_spaces) no loop: the maintainer works there
#   monitor-issues / monitor-pr   only when "monitors" is true (public projects)
#   supervisor                    tab 1 "monitor": supervise.py --loop
# A space still under an old name (legacy_space_names) is renamed, not
# duplicated. A monitor tab that already runs its loop is left alone. One that
# has a Claude in it is reported and left alone: stop it yourself and run this again.
set -euo pipefail
[[ ${HERDR_ENV:-} == 1 ]] || { echo "run this inside Herdr" >&2; exit 1; }
bin=$(cd "$(dirname "$0")" && pwd); repo=$(cd "$bin/../../.." && pwd)
dry=0; [[ ${1:-} == --dry ]] && dry=1
cfgv() { python3 -c "import json;c=json.load(open('$bin/../config.json'));print($1)"; }
d=$(cfgv "c['loops']['dispatch_seconds']"); s=$(cfgv "c['loops']['supervise_seconds']")
t=$(cfgv "c['loops']['triage_seconds']"); p=$(cfgv "c['loops']['prs_seconds']")
ms() { cfgv "c['monitor_spaces']['$1']"; }
# space|loop needle (pgrep)|command|stage   -- an empty needle means no loop.
# Needles carry the full path: another project's loops on this machine must not count.
spaces=("$(cfgv "c.get('product_space', 'product')")|||")
for k in $(cfgv "' '.join(c['stages'])"); do
  spaces+=("$(cfgv "c['stages']['$k']['space']")|$bin/dispatch.py $k --loop|$bin/dispatch.py $k --loop $d|$k")
done
for m in $(cfgv "' '.join(c.get('manual_spaces', []))"); do spaces+=("$m|||"); done
if [[ $(cfgv "bool(c.get('monitors'))") == True ]]; then
  spaces+=("$(ms triage)|$bin/run-loop.sh esteira-triagem|$bin/run-loop.sh esteira-triagem $t|")
  spaces+=("$(ms prs)|$bin/run-loop.sh esteira-monitor-prs|$bin/run-loop.sh esteira-monitor-prs $p|")
fi
spaces+=("$(ms supervisor)|$bin/supervise.py --loop|$bin/supervise.py --loop $s|")
js() { python3 -c "import json,sys;d=json.load(sys.stdin)['result'];print($1)"; }
ws_by_label() { herdr workspace list | js "next((w['workspace_id'] for w in d['workspaces'] if w['label']=='$1'),'')"; }
for entry in "${spaces[@]}"; do
  IFS='|' read -r space needle cmd stage <<<"$entry"
  ws=$(ws_by_label "$space")
  if [[ -z $ws ]]; then
    old=$(cfgv "next((o for o,n in c.get('legacy_space_names',{}).items() if n=='$space'),'')")
    [[ -n $old ]] && ws=$(ws_by_label "$old")
    if [[ -n $ws ]]; then
      echo "~ space $old -> $space"
      ((dry)) || herdr workspace rename "$ws" "$space" >/dev/null
    else
      echo "+ space $space"
      ((dry)) && continue
      ws=$(herdr workspace create --cwd "$repo" --label "$space" --no-focus | js "d['workspace']['workspace_id']")
    fi
  fi
  if [[ -z $needle ]]; then
    echo "= $space: ok (no loop)"
    continue
  fi
  tab=$(herdr tab list --workspace "$ws" | js "sorted(d['tabs'],key=lambda t:t['number'])[0]['tab_id']")
  pane=$(herdr pane list --workspace "$ws" | js "[p['pane_id'] for p in d['panes'] if p['tab_id']=='$tab'][0]")
  agent=$(herdr pane list --workspace "$ws" | js "[p.get('agent') or '' for p in d['panes'] if p['tab_id']=='$tab'][0]")
  # Anchored on "<interpreter> <full script path>": a bare needle also matches
  # any shell whose command line merely mentions it, and the loop is skipped.
  if pgrep -f -- "^[^ ]+ $needle" >/dev/null; then
    echo "= $space: loop already running"
  elif [[ -n $agent ]]; then
    echo "! $space: tab 1 has a $agent session; close it (/exit) and run this again"
  else
    echo "> $space: starting ${needle##*/}"
    if ((!dry)); then herdr tab rename "$tab" monitor >/dev/null; herdr pane run "$pane" "$cmd" >/dev/null; fi
  fi
  if [[ -n $stage ]] && ((!dry)); then "$bin/dispatch.py" seats "$stage" >/dev/null || echo "! $space: could not open seats"; fi
done
