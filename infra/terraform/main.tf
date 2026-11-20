# One k3s node on Graviton in the default VPC. No SSH: administration goes through
# AWS Systems Manager (Session Manager and Run Command), so port 22 is never open.

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

# Canonical publishes the current Ubuntu 24.04 LTS arm64 AMI ID as a public SSM parameter,
# so no AMI ID is hardcoded. The SSM agent comes preinstalled.
data "aws_ssm_parameter" "ubuntu_arm64" {
  name = "/aws/service/canonical/ubuntu/server/24.04/stable/current/arm64/hvm/ebs-gp3/ami-id"
}

locals {
  name = "orbit-telemetry"
  # nip.io resolves orbit.<ip>.nip.io to <ip>: a working hostname without buying a domain.
  app_host = "orbit.${aws_eip.app.public_ip}.nip.io"
}

# ---------------------------------------------------------------------------
# Network: only HTTP and HTTPS in, for the app through Traefik. The Kubernetes API (6443)
# and SSH (22) are not reachable from the internet.
# ---------------------------------------------------------------------------

resource "aws_security_group" "app" {
  name        = "${local.name}-node"
  description = "orbit-telemetry k3s node: web traffic in, anything out"
  vpc_id      = data.aws_vpc.default.id
}

#trivy:ignore:AVD-AWS-0107 Public web app: HTTP must be reachable from anywhere.
resource "aws_vpc_security_group_ingress_rule" "http" {
  security_group_id = aws_security_group.app.id
  description       = "HTTP to Traefik"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
}

#trivy:ignore:AVD-AWS-0107 Public web app: HTTPS must be reachable from anywhere.
resource "aws_vpc_security_group_ingress_rule" "https" {
  security_group_id = aws_security_group.app.id
  description       = "HTTPS to Traefik"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

#trivy:ignore:AVD-AWS-0104 Egress needed for CelesTrak, GHCR, GitHub, k3s and Helm downloads, and the SSM endpoints; no NAT or endpoints in a single-node demo.
resource "aws_vpc_security_group_egress_rule" "all" {
  security_group_id = aws_security_group.app.id
  description       = "Outbound to the internet"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1"
}

# ---------------------------------------------------------------------------
# Instance identity: only what the SSM agent needs to register and take commands.
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "node" {
  name               = "${local.name}-node"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "node_ssm" {
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "node" {
  name = "${local.name}-node"
  role = aws_iam_role.node.name
}

# ---------------------------------------------------------------------------
# The node. A fixed public IP (Elastic IP) so the hostname survives stop and start.
# ---------------------------------------------------------------------------

resource "aws_eip" "app" {
  domain = "vpc"
  tags   = { Name = local.name }
}

resource "aws_instance" "node" {
  ami                    = nonsensitive(data.aws_ssm_parameter.ubuntu_arm64.value) # an AMI ID is not secret
  instance_type          = var.instance_type
  subnet_id              = sort(data.aws_subnets.default.ids)[0]
  vpc_security_group_ids = [aws_security_group.app.id]
  iam_instance_profile   = aws_iam_instance_profile.node.name

  # Burstable CPU: "standard" throttles when credits run out instead of billing extra.
  credit_specification {
    cpu_credits = "standard"
  }

  # IMDSv2 only, and a hop limit of 1 so containers (one network hop further away) cannot
  # reach the instance's credentials.
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  root_block_device {
    volume_type           = "gp3"
    volume_size           = var.root_volume_gb
    encrypted             = true
    delete_on_termination = true
  }

  # cloud-init runs once, on first boot: a changed bootstrap means a new instance.
  user_data = templatefile("${path.module}/templates/cloud-init.yaml.tftpl", {
    k3s_version   = var.k3s_version
    helm_version  = var.helm_version
    helm_sha256   = var.helm_sha256_arm64
    app_host      = local.app_host
    deploy_script = file("${path.module}/files/deploy.sh")
  })
  user_data_replace_on_change = true

  tags = { Name = local.name }

  lifecycle {
    # The AMI parameter moves to newer images over time; do not replace the node for that.
    ignore_changes = [ami]
  }
}

resource "aws_eip_association" "app" {
  instance_id   = aws_instance.node.id
  allocation_id = aws_eip.app.id
}
