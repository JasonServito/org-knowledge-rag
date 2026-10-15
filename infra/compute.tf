# The server (ADR-014 D2, D4; m12): one EC2 instance running Docker, its IAM role, and the boot
# script that installs Docker and writes the deploy script (c1).

data "aws_caller_identity" "current" {}

# The latest Amazon Linux 2023 image for x86 (t3a is AMD x86), from AWS's public SSM parameter.
data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_instance" "server" {
  ami                         = data.aws_ssm_parameter.al2023_ami.insecure_value
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public.id
  vpc_security_group_ids      = [aws_security_group.server.id]
  associate_public_ip_address = true
  iam_instance_profile        = aws_iam_instance_profile.server.name

  # The boot script needs the internet (dnf, once): wait for the subnet's route to the gateway.
  depends_on = [aws_route_table_association.public]

  # Runs once, as root, at the first boot. It starts no container (c1): the first start is the
  # runbook's `orgknow-deploy <tag>`; after a reboot, Docker's restart policy brings both back.
  user_data = templatefile("${path.module}/boot.sh.tftpl", {
    region         = var.region
    registry       = split("/", aws_ecr_repository.app.repository_url)[0]
    repository_url = aws_ecr_repository.app.repository_url
    bucket         = aws_s3_bucket.data.bucket
    log_group      = aws_cloudwatch_log_group.app.name
  })

  # Standard mode: out of CPU credits, the server slows down to its baseline and never bills
  # extra (D2). T3a launches in unlimited mode unless told otherwise.
  credit_specification {
    cpu_credits = "standard"
  }

  # IMDSv2 only: the role's credentials need a session token, which a forged GET can't get (m12).
  metadata_options {
    http_tokens = "required"
  }

  root_block_device {
    volume_size = 20
    volume_type = "gp3"
    encrypted   = true
  }

  # The AMI parameter points at a newer image every few weeks; without this, the next apply would
  # replace the server (and lose its unpacked corpus and env file). Replace it on purpose with
  # `terraform apply -replace=aws_instance.server`.
  lifecycle {
    ignore_changes = [ami]
  }
}

# The server's role (D6): Session Manager (shell and tunnel, no SSH) plus one inline policy that
# reads only /orgknow/*, pulls only the one repository, reads only the one bucket, and writes only
# the one log group.
resource "aws_iam_role" "server" {
  name = "orgknow-server"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.server.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy" "server" {
  name = "orgknow-server"
  role = aws_iam_role.server.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        # The deploy script reads every /orgknow/* value in one call (GetParametersByPath with the
        # path /orgknow). That call is checked against the path's own ARN (parameter/orgknow), so
        # it is listed too; no parameter has that name, so it grants nothing else. Decrypting
        # SecureStrings with the AWS-managed aws/ssm key needs no KMS statement: that key's policy
        # allows the account's principals through SSM.
        Sid    = "ReadOrgknowParameters"
        Effect = "Allow"
        Action = ["ssm:GetParametersByPath", "ssm:GetParameters", "ssm:GetParameter"]
        Resource = [
          "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/orgknow",
          "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter/orgknow/*",
        ]
      },
      {
        # The ECR login token is account-wide: this action takes no narrower resource.
        Sid      = "EcrLogin"
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Sid      = "PullOneRepository"
        Effect   = "Allow"
        Action   = ["ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer", "ecr:BatchCheckLayerAvailability"]
        Resource = aws_ecr_repository.app.arn
      },
      {
        Sid      = "ReadOneBucket"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${aws_s3_bucket.data.arn}/*"
      },
      {
        Sid      = "ListOneBucket"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = aws_s3_bucket.data.arn
      },
      {
        # Docker's awslogs driver: the group itself and its streams (api, worker).
        Sid      = "WriteOneLogGroup"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = [aws_cloudwatch_log_group.app.arn, "${aws_cloudwatch_log_group.app.arn}:*"]
      },
    ]
  })
}

resource "aws_iam_instance_profile" "server" {
  name = "orgknow-server"
  role = aws_iam_role.server.name
}
