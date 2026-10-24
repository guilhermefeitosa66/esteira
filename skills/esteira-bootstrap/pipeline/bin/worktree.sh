#!/usr/bin/env bash
# Idempotent worktree for a pipeline job: prints its path.
#   worktree.sh <stage> <issue> <branch> [--new]      --new: create <branch> off the base branch
#   worktree.sh <stage> <issue> --detach [ref]         detached (review/qa check a PR out afterwards)
# Prints the project's folder inside the worktree: the worktree root, or
# <root>/<subdir> in a monorepo (`subdir` in the config). To remove it, use
# the root: git -C <printed path> rev-parse --show-toplevel.
# An existing worktree is reused when it is on the same branch. Uncommitted
# changes found in one are saved to salvage/<stage>-<issue>-<date>.patch first,
# then the tree is reset to the branch's remote head -- nothing is ever lost.
set -euo pipefail
stage=$1 issue=$2; shift 2
cfg=$(dirname "$0")/../config.json
j() { python3 -c "import json,os;c=json.load(open('$cfg'));print(os.path.expanduser($1))"; }
main=$(cd "$(dirname "$0")/../../.." && pwd)
wtdir=$(j "c['worktrees_dir']"); base=$(j "c.get('base_branch','main')")
state=$(j "c['state_dir']"); mkdir -p "$wtdir" "$state/salvage"
ssh=$(j "c.get('git_ssh_command','')"); [[ -n $ssh ]] && export GIT_SSH_COMMAND="$ssh"
wt="$wtdir/$stage-$issue"
sub=$(j "c.get('subdir','')")
show() {
  if [[ -n $sub && ! -d $wt/$sub ]]; then
    echo "worktree.sh: $sub does not exist in this branch; using the worktree root" >&2; echo "$wt"
  else
    echo "$wt${sub:+/$sub}"
  fi
}
git -C "$main" fetch -q origin
if [[ -d $wt ]]; then
  if [[ -n $(git -C "$wt" status --porcelain 2>/dev/null) ]]; then
    p="$state/salvage/$stage-$issue-$(date +%Y%m%d%H%M%S).patch"
    git -C "$wt" diff HEAD > "$p"; git -C "$wt" status --porcelain >> "$p"
    echo "worktree.sh: uncommitted changes saved to $p" >&2
  fi
  if [[ ${1:-} != --detach ]] && [[ $(git -C "$wt" rev-parse --abbrev-ref HEAD 2>/dev/null) == "$1" ]]; then
    git -C "$wt" reset -q --hard; git -C "$wt" clean -qfd
    git -C "$wt" pull -q --rebase origin "$1" 2>/dev/null || true
    show; exit 0
  fi
  git -C "$main" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  git -C "$main" worktree prune
fi
case ${1:-} in
  --detach) git -C "$main" worktree add -q --detach "$wt" "${2:-origin/$base}" ;;
  *)
    branch=$1
    if [[ ${2:-} == --new ]] && ! git -C "$main" rev-parse -q --verify "refs/remotes/origin/$branch" >/dev/null; then
      git -C "$main" worktree add -q "$wt" -b "$branch" "origin/$base"
    else
      git -C "$main" worktree add -q "$wt" "$branch" 2>/dev/null \
        || git -C "$main" worktree add -q "$wt" -B "$branch" "origin/$branch"
      git -C "$wt" pull -q --rebase origin "$branch" 2>/dev/null || true
    fi ;;
esac
show
