# Continuous deployment without stored AWS keys. GitHub Actions issues a short-lived OIDC
# token for each run; AWS trusts it only for this repository's "production" environment,
# and the role it grants can do one thing: run a command on this one instance.

locals {
  github_oidc_url = "https://token.actions.githubusercontent.com"
  github_owner    = split("/", var.github_repository)[0]
  github_repo     = split("/", var.github_repository)[1]

  # Immutable subject: names plus permanent numeric IDs, so a deleted-and-recreated or
  # renamed repository with the same name can never inherit this trust.
  github_deploy_subject = "repo:${local.github_owner}@${var.github_owner_id}/${local.github_repo}@${var.github_repository_id}:environment:production"
  github_oidc_arn       = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : data.aws_iam_openid_connect_provider.github[0].arn
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_github_oidc_provider ? 1 : 0
  url            = local.github_oidc_url
  client_id_list = ["sts.amazonaws.com"]
}

data "aws_iam_openid_connect_provider" "github" {
  count = var.create_github_oidc_provider ? 0 : 1
  url   = local.github_oidc_url
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [local.github_oidc_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Only jobs that declare `environment: production` in this exact repository (matched by
    # its permanent IDs). A pull request, another branch or a fork gets a different subject.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [local.github_deploy_subject]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name                 = "${local.name}-github-deploy"
  description          = "Assumed by GitHub Actions (production environment) to deploy via SSM"
  assume_role_policy   = data.aws_iam_policy_document.github_assume.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "github_deploy" {
  statement {
    sid     = "RunDeployCommandOnTheNode"
    actions = ["ssm:SendCommand"]
    resources = [
      aws_instance.node.arn,
      "arn:aws:ssm:${var.aws_region}::document/AWS-RunShellScript",
    ]
  }

  # GetCommandInvocation does not support resource-level permissions, so it needs "*".
  # It only reads the output of commands, it cannot run anything.
  statement {
    sid       = "ReadDeployCommandResult"
    actions   = ["ssm:GetCommandInvocation"]
    resources = ["*"]
  }
}

#trivy:ignore:AVD-AWS-0057 ssm:GetCommandInvocation has no resource-level permissions; read-only.
resource "aws_iam_role_policy" "github_deploy" {
  name   = "deploy-via-ssm"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
