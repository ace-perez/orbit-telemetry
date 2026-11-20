provider "aws" {
  region = var.aws_region

  # Every resource gets these tags, so cost and ownership are visible in the console and
  # in Cost Explorer (filter by Project = orbit-telemetry).
  default_tags {
    tags = {
      Project   = "orbit-telemetry"
      ManagedBy = "terraform"
      Owner     = var.owner
    }
  }
}
