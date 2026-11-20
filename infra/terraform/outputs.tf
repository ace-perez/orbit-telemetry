output "instance_id" {
  description = "The k3s node. Repository variable EC2_INSTANCE_ID."
  value       = aws_instance.node.id
}

output "public_ip" {
  description = "Elastic IP of the node."
  value       = aws_eip.app.public_ip
}

output "app_host" {
  description = "Public hostname (nip.io). Repository variable APP_HOST."
  value       = local.app_host
}

output "app_url" {
  description = "Open this once the first deploy has finished."
  value       = "http://${local.app_host}/docs"
}

output "deploy_role_arn" {
  description = "Role GitHub Actions assumes. Repository variable AWS_DEPLOY_ROLE_ARN."
  value       = aws_iam_role.github_deploy.arn
}

output "ami_id" {
  description = "Ubuntu 24.04 arm64 image the node was built from."
  value       = aws_instance.node.ami
}
