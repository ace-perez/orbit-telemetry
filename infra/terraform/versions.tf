terraform {
  # 1.10+ for S3-native state locking (use_lockfile), so no DynamoDB table is needed.
  required_version = ">= 1.10"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.73"
    }
  }

  # Remote state in S3, created once by hand (Phase 6, Step 2). The bucket name contains the
  # account ID, so it is passed at init time instead of being committed:
  #   terraform init -backend-config="bucket=orbit-telemetry-tfstate-<account-id>"
  backend "s3" {
    key          = "orbit-telemetry/production.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}
