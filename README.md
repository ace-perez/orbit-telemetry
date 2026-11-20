# Orbit Telemetry

Satellite telemetry API (real orbits from CelesTrak, simulated spacecraft subsystems) delivered through a
complete CI/CD pipeline: GitHub Actions, Docker, Helm on k3s (AWS EC2), Terraform, SonarQube Cloud, Trivy,
Prometheus, Grafana and Loki.

> Status: in development.

## Architecture
Diagram added in Phase 8.

## Pipeline
| Stage | Tooling | Enforcement |
|---|---|---|
| Source control | GitHub Flow, protected main, SemVer releases | Branch ruleset |
| Build and test | uv, pytest (unit and integration), kind | Coverage gate |
| Static analysis and security | Ruff, Bandit, SonarQube Cloud, Trivy, Gitleaks, Hadolint | Fails on HIGH/CRITICAL |
| Containerisation | Multi-stage Docker image, non-root | Trivy image scan |
| Deployment | Terraform, k3s, Helm, AWS SSM, GitHub OIDC | Atomic, metric-gated rollback |
| Monitoring and logging | Prometheus, Alertmanager, Grafana, Loki, Alloy | Alerts to Discord |


## Cost
Runs on a single EC2 instance only while needed; `terraform destroy` removes everything.

![CI](https://github.com/ace-perez/orbit-telemetry/actions/workflows/ci.yml)