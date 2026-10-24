#!/usr/bin/env bash
# Run a command holding a machine-wide lock, so two workers never share a
# resource that only fits one at a time (a test display, an emulator, a big
# container, a port).
#   lock.sh <name> <command...>        e.g. lock.sh e2e npm run test:e2e
# Who holds it is written next to the lock (<name>.owner) for esteira-status;
# it waits up to an hour, then gives up with exit code 75.
set -euo pipefail
name=${1:?usage: lock.sh <name> <command...>}; shift
[[ $name =~ ^[a-zA-Z0-9_-]+$ ]] || { echo "lock name: letters, digits, - and _ only" >&2; exit 2; }
state=$(eval echo "$(python3 -c "import json;print(json.load(open('$(dirname "$0")/../config.json'))['state_dir'])")")
mkdir -p "$state"
exec 9>"$state/$name.lock"
flock -w 3600 9 || { echo "$name busy for an hour; giving up" >&2; exit 75; }
python3 -c 'import json,sys,time;print(json.dumps({"pid":int(sys.argv[1]),"since":int(time.time()),"cwd":sys.argv[2],"cmd":" ".join(sys.argv[3:])}))' "$$" "$PWD" "$@" > "$state/$name.owner"
trap 'rm -f "$state/$name.owner"' EXIT
"$@"
