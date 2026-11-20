variable "aws_region" {
  description = "Region for every resource."
  type        = string
  default     = "eu-west-1"
}

variable "owner" {
  description = "Value of the Owner tag."
  type        = string
  default     = "ace-perez"
}

variable "github_repository" {
  description = "owner/name of the repository allowed to deploy through GitHub OIDC."
  type        = string
  default     = "ace-perez/orbit-telemetry"
}

# GitHub's immutable OIDC subject (the default for repositories created after 15 Jul 2026)
# includes the owner's and repository's numeric IDs, which never change or get reused:
#   repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:<name>
# Find them with: gh api repos/ace-perez/orbit-telemetry --jq '.owner.id, .id'
variable "github_owner_id" {
  description = "Numeric ID of the repository owner (gh api repos/OWNER/REPO --jq .owner.id)."
  type        = string
  default     = "43325579"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "Must be the numeric owner ID from the GitHub API."
  }
}

variable "github_repository_id" {
  description = "Numeric ID of the repository (gh api repos/OWNER/REPO --jq .id)."
  type        = string
  default     = "1464618752"

  validation {
    condition     = can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "Must be the numeric repository ID from the GitHub API."
  }
}

variable "create_github_oidc_provider" {
  description = "Create GitHub's OIDC identity provider. Set false if the account already has one (only one per URL is allowed)."
  type        = bool
  default     = true
}

variable "instance_type" {
  description = "Graviton (arm64) instance. t4g.large: 2 vCPU, 8 GiB. Post-project, a t4g.micro runs the Docker-only setup."
  type        = string
  default     = "t4g.large"

  validation {
    condition     = startswith(var.instance_type, "t4g.") || startswith(var.instance_type, "m7g.") || startswith(var.instance_type, "c7g.")
    error_message = "The image is built for arm64, so use a Graviton instance type (t4g, m7g or c7g)."
  }
}

variable "root_volume_gb" {
  description = "Root disk size. k3s, container images and Prometheus data live here."
  type        = number
  default     = 30
}

variable "k3s_version" {
  description = "Pinned k3s release, matching the Kubernetes 1.37 schemas CI validates against."
  type        = string
  default     = "v1.37.2+k3s1"
}

variable "helm_version" {
  description = "Helm on the server, the same version CI uses."
  type        = string
  default     = "4.3.2"
}

variable "helm_sha256_arm64" {
  description = "SHA-256 of helm-v<version>-linux-arm64.tar.gz from get.helm.sh (Phase 6, Step 1)."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{64}$", var.helm_sha256_arm64))
    error_message = "Must be a 64-character lowercase hex SHA-256."
  }
}

variable "alert_email" {
  description = "Where AWS Budgets sends cost alerts."
  type        = string
}

variable "monthly_budget_usd" {
  description = "Monthly cost budget. Alerts at 50% and 100% of actual spend, and at 100% forecast."
  type        = number
  default     = 20
}
