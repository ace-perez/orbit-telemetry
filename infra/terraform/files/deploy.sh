#!/usr/bin/env bash
# Deploys one commit of orbit-telemetry to the local k3s cluster.
# Called by the CI deploy job through SSM Run Command, as root:
#   /opt/orbit/deploy.sh <40-character git commit SHA> <image tag, sha-xxxxxxx>
#
# The chart and values come from the same commit as the image, so what runs is exactly what
# was reviewed and tested. Post-project, this script is the only thing that changes when the
# runtime moves from k3s to Docker Compose: CI keeps calling it the same way.
set -euo pipefail

SHA="${1:-}"
TAG="${2:-}"
REPO_URL="https://github.com/ace-perez/orbit-telemetry"
RELEASE="orbit-telemetry"
NAMESPACE="orbit"

# The arguments arrive from outside (CI through SSM), so accept only the expected shapes.
[[ "$SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "error: commit must be a 40-character SHA" >&2; exit 2; }
[[ "$TAG" =~ ^sha-[0-9a-f]{7}$ ]] || { echo "error: tag must look like sha-1a2b3c4" >&2; exit 2; }

# shellcheck source=/dev/null
source /opt/orbit/env # APP_HOST, written by cloud-init
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

echo "==> Waiting for the node to be Ready"
kubectl wait --for=condition=Ready node --all --timeout=180s

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "==> Fetching chart and values at ${SHA}"
git clone --quiet --filter=blob:none --no-checkout "$REPO_URL" "$WORK/src"
git -C "$WORK/src" checkout --quiet "$SHA"

echo "==> Deploying ${TAG} to ${APP_HOST}"
helm upgrade --install "$RELEASE" "$WORK/src/charts/orbit-telemetry" \
  --namespace "$NAMESPACE" --create-namespace \
  --values "$WORK/src/deploy/ec2/values-ec2.yaml" \
  --set image.tag="$TAG" \
  --set ingress.host="$APP_HOST" \
  --wait --timeout 5m \
  --rollback-on-failure

echo "==> Post-deploy test"
helm test "$RELEASE" --namespace "$NAMESPACE" --logs

echo "==> Release history"
helm history "$RELEASE" --namespace "$NAMESPACE" --max 5
