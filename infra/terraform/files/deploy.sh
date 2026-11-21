#!/usr/bin/env bash
# Entry point the CI deploy job calls through SSM Run Command, as root:
#   /opt/orbit/deploy.sh <40-character git commit SHA> <image tag, sha-xxxxxxx>
#
# It only validates its input and checks out that exact commit; the release itself is
# deploy/ec2/release.sh from the same commit, so release logic changes through pull requests
# like everything else instead of being baked into the server at first boot.
set -euo pipefail

SHA="${1:-}"
TAG="${2:-}"
REPO_URL="https://github.com/ace-perez/orbit-telemetry"

# The arguments arrive from outside (CI through SSM), so accept only the expected shapes.
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "error: commit must be a 40-character SHA" >&2; exit 2; }
[[ "$TAG" =~ ^sha-[0-9a-f]{7}$ ]] || { echo "error: tag must look like sha-1a2b3c4" >&2; exit 2; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> Fetching ${SHA}"
git clone --quiet --filter=blob:none --no-checkout "$REPO_URL" "$WORK/src"
git -C "$WORK/src" checkout --quiet "$SHA"

bash "$WORK/src/deploy/ec2/release.sh" "$WORK/src" "$TAG"
