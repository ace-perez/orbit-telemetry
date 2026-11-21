#!/usr/bin/env bash
# Installs the observability platform on the k3s node (Phase 7): kube-prometheus-stack
# (Prometheus, Alertmanager, Grafana), Loki and Grafana Alloy, plus their secrets.
# Run as root on the node from a clone of the repository:
#   sudo bash deploy/platform/install.sh
# Safe to re-run: every step creates or upgrades.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
PLATFORM="$REPO_DIR/deploy/platform"
REGION="eu-west-1"
NS="monitoring"
KPS_VERSION="93.6.0"
LOKI_VERSION="7.7.0"
ALLOY_VERSION="1.16.0"
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml

echo "==> AWS CLI, to read secrets from SSM Parameter Store with the node's role"
command -v aws >/dev/null || snap install aws-cli --classic

param() {
  aws ssm get-parameter --region "$REGION" --name "$1" --with-decryption \
    --query Parameter.Value --output text | tr -d '\n'
}

echo "==> Namespace and secrets (values go straight from SSM into Kubernetes, never to disk)"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
param /orbit-telemetry/discord-webhook-url |
  kubectl -n "$NS" create secret generic alertmanager-discord \
    --from-file=webhook-url=/dev/stdin --dry-run=client -o yaml | kubectl apply -f -
param /orbit-telemetry/grafana-admin-password |
  kubectl -n "$NS" create secret generic grafana-admin \
    --from-literal=admin-user=admin --from-file=admin-password=/dev/stdin \
    --dry-run=client -o yaml | kubectl apply -f -

echo "==> Helm repositories"
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts --force-update
helm repo add grafana https://grafana.github.io/helm-charts --force-update
helm repo update

echo "==> kube-prometheus-stack ${KPS_VERSION}"
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --version "$KPS_VERSION" --namespace "$NS" \
  --values "$PLATFORM/kube-prometheus-stack.values.yaml" \
  --wait --timeout 10m

echo "==> Loki ${LOKI_VERSION}"
helm upgrade --install loki grafana/loki \
  --version "$LOKI_VERSION" --namespace "$NS" \
  --values "$PLATFORM/loki.values.yaml" \
  --wait --timeout 10m

echo "==> Grafana Alloy ${ALLOY_VERSION}"
helm upgrade --install alloy grafana/alloy \
  --version "$ALLOY_VERSION" --namespace "$NS" \
  --values "$PLATFORM/alloy.values.yaml" \
  --wait --timeout 5m

echo "==> Deploy entry point on the node (thin wrapper; release logic lives in the repo)"
install -m 0750 "$REPO_DIR/infra/terraform/files/deploy.sh" /opt/orbit/deploy.sh

echo "==> Status"
kubectl -n "$NS" get pods
helm list --all-namespaces
echo "Grafana ClusterIP for the SSM port-forward: $(kubectl -n "$NS" get svc kps-grafana -o jsonpath='{.spec.clusterIP}')"
