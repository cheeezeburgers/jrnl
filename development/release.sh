#!/usr/bin/env bash
# Maintainer commands behind make tag/release; installation stays in install.sh.
set -Eeuo pipefail

fail() { printf '[ X ] %s\n' "$*" >&2; exit 1; }
(( $# == 1 )) && [[ $1 == tag || $1 == release ]] || fail 'Usage: bash development/release.sh tag|release'
action=$1
command -v git >/dev/null 2>&1 || fail 'git is required.'
if [[ $action == release ]]; then
    command -v gh >/dev/null 2>&1 || fail 'gh is required; install GitHub CLI and authenticate with gh auth login.'
fi
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
root=$(pwd -P)
[[ $(git rev-parse --show-toplevel) == "$root" ]] || fail 'Run from a complete jrnl Git checkout.'
head=$(git rev-parse --verify 'HEAD^{commit}') || fail 'HEAD must contain a commit.'
status=$(git status --porcelain --untracked-files=all --ignore-submodules=none)
[[ -z $status ]] || fail 'Working tree must be clean, including staged and untracked files; commit or move changes first.'
for state in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply sequencer BISECT_LOG; do
    [[ ! -e $(git rev-parse --git-path "$state") ]] || fail "Finish the in-progress Git operation ($state) first."
done
git ls-files --error-unmatch jrnl.sh >/dev/null || fail 'The canonical version source jrnl.sh must be tracked.'
version_output=$(./jrnl.sh --version) || fail 'Cannot read the canonical version from jrnl.sh.'
[[ $version_output =~ ^jrnl\ ([0-9]+\.[0-9]+\.[0-9]+[ab]?)$ ]] || fail "Invalid project version: $version_output"
version=${BASH_REMATCH[1]}
tag=v$version
ref=refs/tags/$tag

if [[ $action == tag ]]; then
    if git show-ref --verify --quiet "$ref"; then
        fail "Tag $tag already exists; it will not be replaced."
    fi
    git tag -a "$tag" -m "jrnl $tag" "$head"
    printf '[ OK ] Created local annotated tag %s. Nothing pushed.\n' "$tag"
    exit 0
fi

# Release only an existing annotated tag made for this exact commit.
[[ $(git cat-file -t "$ref" 2>/dev/null) == tag ]] || fail "Annotated tag $tag is required; run make tag first."
[[ $(git rev-parse "$ref^{commit}") == "$head" ]] || fail "Tag $tag does not point to HEAD."
tag_object=$(git rev-parse "$ref")

# Use one explicit destination for both Git and gh, regardless of GH_REPO or
# gh's default repository. Refuse ambiguous multi-destination push settings.
remote=$(git remote get-url --push --all origin) || fail 'An origin push URL is required.'
[[ -n $remote && $remote != *$'\n'* ]] || fail 'origin must have exactly one push URL.'
case "$remote" in
    https://*) repository=${remote#https://} ;;
    git@*:*) repository=${remote#git@}; repository=${repository/:/\/} ;;
    ssh://git@*) repository=${remote#ssh://git@} ;;
    *) fail 'origin must use a GitHub HTTPS or SSH URL.' ;;
esac
repository=${repository%.git}
[[ $repository =~ ^([a-zA-Z0-9.-]+)/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)$ ]] || fail 'Cannot determine the GitHub host and repository from origin.'
host=${BASH_REMATCH[1]}
repo=${BASH_REMATCH[2]}
gh auth status --hostname "$host" >/dev/null || fail "Authenticate with gh auth login --hostname $host first."
permission=$(gh api --hostname "$host" "repos/$repo" --jq '.permissions.push') || fail 'Cannot access the release repository.'
[[ $permission == true ]] || fail 'GitHub write permission is required to release.'
# Listing successfully distinguishes absence from auth/network failures, and
# includes drafts. Paginate so older releases are checked too.
existing=$(gh api --hostname "$host" --paginate "repos/$repo/releases?per_page=100" \
    --jq ".[] | select(.tag_name == \"$tag\") | .tag_name") || fail 'Cannot check existing releases; nothing pushed.'
[[ -z $existing ]] || fail "GitHub release $tag already exists; it will not be replaced."
remote_tags=$(git ls-remote --tags "$remote" "$ref" "$ref^{}") || fail 'Cannot check remote tags; nothing pushed.'
while read -r object name; do
    [[ -n $object ]] || continue
    case "$name" in
        "$ref") [[ $object == "$tag_object" ]] || fail "Remote tag $tag differs from the local tag." ;;
        "$ref^{}") [[ $object == "$head" ]] || fail "Remote tag $tag does not point to HEAD." ;;
    esac
done <<< "$remote_tags"

# Explicit refspec and disabled follow-tags/mirroring prevent unrelated pushes.
git push --no-follow-tags --no-mirror --recurse-submodules=no "$remote" "$ref:$ref" || fail 'Tag push failed; release was not created.'
gh release create "$tag" --repo "$repository" --verify-tag \
    --title "jrnl $tag" --generate-notes || fail "Release creation failed. Tag $tag remains on origin; inspect GitHub before retrying."
