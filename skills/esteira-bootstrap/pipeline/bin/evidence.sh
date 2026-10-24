#!/usr/bin/env bash
# Publish evidence files (images, videos) to the evidence repo and print one
# Markdown line per file, ready to paste into an issue comment: images as
# inline images, anything else (a video) as a link.
#
#   evidence.sh qa|design <issue> <run-id> <file>...
#
# Serialised with flock: several workers can publish at the same time. Links are
# pinned to the commit, so a later push can never change what a comment shows.
set -euo pipefail
kind=$1 issue=$2 run=$3; shift 3
[[ $kind == qa || $kind == design ]] || { echo "kind must be qa or design" >&2; exit 2; }
cfg=$(dirname "$0")/../config.json
j() { python3 -c "import json,os;c=json.load(open('$cfg'));print(os.path.expanduser($1))"; }
repo=$(j "c['evidence_repo']"); dir=$(j "c['evidence_checkout']"); state=$(j "c['state_dir']")
ssh=$(j "c.get('git_ssh_command','')"); [[ -n $ssh ]] && export GIT_SSH_COMMAND="$ssh"
mkdir -p "$state"
exec 9>"$state/evidence.lock"; flock 9
[[ -d $dir/.git ]] || gh repo clone "$repo" "$dir" -- -q
cd "$dir"
branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo main)
git pull -q --rebase origin "$branch" 2>/dev/null || true
dest="$kind/issue-$issue/$run"; mkdir -p "$dest"
for f in "$@"; do cp "$f" "$dest/"; done
git add "$dest"
git commit -qm "evidence: $kind for issue $issue ($run)" || true
git push -q origin "HEAD:$branch"
sha=$(git rev-parse HEAD)
for f in "$@"; do
  b=$(basename "$f"); alt=${b%.*}; alt=${alt//-/ }
  case ${b,,} in
    *.png|*.jpg|*.jpeg|*.gif|*.webp|*.svg) echo "![${alt}](https://raw.githubusercontent.com/$repo/$sha/$dest/$b)" ;;
    *) echo "[${b}](https://github.com/$repo/blob/$sha/$dest/$b)" ;;
  esac
done
