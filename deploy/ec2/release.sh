#!/usr/bin/env bash
# One release of orbit-telemetry to k3s. Called by /opt/orbit/deploy.sh as root with the
# checked-out repository and the image tag:  release.sh <repo dir> <sha-xxxxxxx>
#
#   1. helm upgrade --install --wait --rollback-on-failure: if the new pods never become
#      Ready, Helm restores the previous release by itself.
#   2. helm test: /readyz through the Service.
#   3. Bake (metric-gated rollback): wait, then ask Prometheus for the real API error ratio.
#      Above the limit, roll back to the previous revision and fail the deploy, even though
#      the pods were "healthy". This catches bugs that probes cannot see.
set -euo pipefail

SRC="$1"
TAG="$2"
RELEASE="orbit-telemetry"
NAMESPACE="orbit"
REGION="eu-west-1"
BAKE_SECONDS="${BAKE_SECONDS:-150}"     # longer than the 2-minute query window below
MAX_ERROR_RATIO="${MAX_ERROR_RATIO:-0.05}" # same 5% as the OrbitTelemetryHighErrorRate alert
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
# shellcheck source=/dev/null
source /opt/orbit/env # APP_HOST, written by cloud-init

# Posts to the Discord channel Alertmanager uses, when the platform (and so the webhook
# secret in SSM and the AWS CLI) is installed. Never fails the release by itself.
notify() {
  command -v aws >/dev/null || return 0
  local url
  url="$(aws ssm get-parameter --region "$REGION" --name /orbit-telemetry/discord-webhook-url \
    --with-decryption --query Parameter.Value --output text 2>/dev/null | tr -d '\n')" || return 0
  [ -n "$url" ] || return 0
  jq -n --arg c "$1" '{content: $c}' |
    curl -fsS -m 10 -H 'Content-Type: application/json' -d @- "$url" >/dev/null || true
}

echo "==> Waiting for the node to be Ready"
kubectl wait --for=condition=Ready node --all --timeout=180s

echo "==> Deploying ${TAG} to ${APP_HOST}"
helm upgrade --install "$RELEASE" "$SRC/charts/orbit-telemetry" \
  --namespace "$NAMESPACE" --create-namespace \
  --values "$SRC/deploy/ec2/values-ec2.yaml" \
  --set image.tag="$TAG" \
  --set ingress.host="$APP_HOST" \
  --wait --timeout 5m \
  --rollback-on-failure

echo "==> Post-deploy test"
helm test "$RELEASE" --namespace "$NAMESPACE" --logs

if kubectl -n monitoring get service kps-prometheus >/dev/null 2>&1; then
  echo "==> Bake: measuring the API error ratio after ${BAKE_SECONDS}s of real traffic"
  sleep "$BAKE_SECONDS"
  QUERY='(sum(rate(http_requests_total{job="orbit-telemetry", route=~"/api/.+", status=~"5.."}[2m])) or vector(0)) / sum(rate(http_requests_total{job="orbit-telemetry", route=~"/api/.+"}[2m]))'
  ENCODED="$(jq -rn --arg q "$QUERY" '$q | @uri')"
  # Through the Kubernetes API server's service proxy: no port-forward, no exposed port.
  RATIO="$(kubectl get --raw "/api/v1/namespaces/monitoring/services/kps-prometheus:9090/proxy/api/v1/query?query=${ENCODED}" |
    jq -r '.data.result[0].value[1] // "NaN"')"
  echo "API error ratio over the last 2 minutes: ${RATIO} (limit ${MAX_ERROR_RATIO})"

  if awk -v r="$RATIO" -v m="$MAX_ERROR_RATIO" 'BEGIN { exit !(r != "NaN" && r + 0 > m + 0) }'; then
    echo "==> ${TAG} is failing too many requests: rolling back"
    helm rollback "$RELEASE" --namespace "$NAMESPACE" --wait --timeout 5m
    helm history "$RELEASE" --namespace "$NAMESPACE" --max 5
    notify ":rewind: Deploy \`${TAG}\` rolled back automatically: API error ratio ${RATIO} was above ${MAX_ERROR_RATIO} during the bake."
    exit 1
  fi
else
  echo "==> Monitoring is not installed yet: skipping the bake check"
fi

echo "==> Release history"
helm history "$RELEASE" --namespace "$NAMESPACE" --max 5
notify ":rocket: Deployed \`${TAG}\` to http://${APP_HOST}/docs"
