# Offline tests of the AWS environment (S15-T4): `terraform test` with mocked providers, so no AWS
# account, no credentials and nothing created. Each run block pins one row of the S15 run
# contract's proof map; the expected values come from the contract (decisions 1-3, m9-m13, the
# names table), never from the code under test.
#
# A mocked provider makes up a value for each attribute AWS would compute (an ID, an ARN). Runs
# that compare two such values (a rule's source group, a subnet's route table) use
# `command = apply`, so those values are known; the others only need the plan.

mock_provider "aws" {
  # The provider checks that an alarm's action is an ARN, so the topic gets a realistic one.
  override_resource {
    target = aws_sns_topic.alerts
    values = {
      arn = "arn:aws:sns:us-east-1:123456789012:orgknow-alerts"
    }
  }
  # Data sources would also get made-up values; these two are given realistic ones.
  override_data {
    target = data.aws_ssm_parameter.al2023_ami
    values = {
      insecure_value = "ami-0123456789abcdef0"
    }
  }
  override_data {
    target = data.aws_caller_identity.current
    values = {
      account_id = "123456789012"
    }
  }
}

mock_provider "random" {}

variables {
  alert_email       = "alerts@example.com"
  langfuse_base_url = "https://us.cloud.langfuse.com"
}

# Decision 3: the database has no public address.
run "rds_has_no_public_address" {
  command = plan

  assert {
    condition     = aws_db_instance.main.publicly_accessible == false
    error_message = "RDS must not be publicly accessible (ADR-014 D3)."
  }
}

# Decision 3: the database's subnets have no route to the internet, only the implicit local one.
run "private_subnets_have_no_internet_route" {
  command = apply

  assert {
    condition     = length([for r in aws_route_table.private.route : r if r.cidr_block == "0.0.0.0/0"]) == 0
    error_message = "The private route table has a route to 0.0.0.0/0 (ADR-014 D3)."
  }
  assert {
    condition     = length(aws_route_table.private.route) == 0
    error_message = "The private route table has a route beyond the local one (ADR-014 D3)."
  }
  assert {
    condition = (
      aws_route_table_association.private_a.subnet_id == aws_subnet.private_a.id
      && aws_route_table_association.private_a.route_table_id == aws_route_table.private.id
    )
    error_message = "Private subnet a does not use the private route table."
  }
  assert {
    condition = (
      aws_route_table_association.private_b.subnet_id == aws_subnet.private_b.id
      && aws_route_table_association.private_b.route_table_id == aws_route_table.private.id
    )
    error_message = "Private subnet b does not use the private route table."
  }
}

# Decision 1: nothing can connect in to the server.
run "server_has_no_inbound_rule" {
  command = plan

  assert {
    condition     = length(aws_security_group.server.ingress) == 0
    error_message = "The server's security group has an inbound rule (ADR-014 D1)."
  }
}

# Decision 3: the database admits one thing: Postgres's port, from the server's group.
run "database_admits_only_the_server" {
  command = apply

  assert {
    condition     = length(aws_security_group.db.ingress) == 1
    error_message = "The database's security group must have exactly 1 inbound rule (ADR-014 D3)."
  }
  assert {
    condition = alltrue([
      for rule in aws_security_group.db.ingress : (
        rule.protocol == "tcp" && rule.from_port == 5432 && rule.to_port == 5432
        && rule.security_groups == toset([aws_security_group.server.id])
        && length(coalesce(rule.cidr_blocks, [])) == 0
        && length(coalesce(rule.ipv6_cidr_blocks, [])) == 0
        && length(coalesce(rule.prefix_list_ids, [])) == 0
        && !coalesce(rule.self, false)
      )
    ])
    error_message = "The database's inbound rule must be TCP 5432 from the server's group only (ADR-014 D3)."
  }
}

# The security-group and route checks above read each resource's own rule list. A rule written as
# a separate resource would not be in that list, so the code has none: this run fails if one
# appears in any .tf file.
run "rules_are_inline" {
  command = plan

  assert {
    condition = length(regexall(
      "resource\\s+\"aws_(security_group_rule|vpc_security_group_ingress_rule|vpc_security_group_egress_rule)\"",
      join("\n", [for f in fileset(path.module, "*.tf") : file("${path.module}/${f}")])
    )) == 0
    error_message = "A security-group rule is a separate resource: write it inline in its group, so the tests see it."
  }
  assert {
    condition = length(regexall(
      "resource\\s+\"aws_route\"",
      join("\n", [for f in fileset(path.module, "*.tf") : file("${path.module}/${f}")])
    )) == 0
    error_message = "A route is a separate resource: write it inline in its route table, so the tests see it."
  }
}

# Decision 2 and m12: the default type, credits that never bill extra, and IMDSv2 only.
run "instance_and_credits" {
  command = plan

  assert {
    condition     = aws_instance.server.instance_type == "t3a.medium"
    error_message = "The default instance type must be t3a.medium (ADR-014 D2)."
  }
  assert {
    condition     = aws_instance.server.credit_specification[0].cpu_credits == "standard"
    error_message = "CPU credits must be in standard mode (ADR-014 D2)."
  }
  assert {
    condition     = aws_instance.server.metadata_options[0].http_tokens == "required"
    error_message = "The instance must require IMDSv2 (m12)."
  }
}

# m10: US$50 a month; email at 80% actual and 100% forecast.
run "budget" {
  command = plan

  assert {
    condition = (
      aws_budgets_budget.monthly.budget_type == "COST"
      && aws_budgets_budget.monthly.limit_amount == "50"
      && aws_budgets_budget.monthly.limit_unit == "USD"
      && aws_budgets_budget.monthly.time_unit == "MONTHLY"
    )
    error_message = "The budget must be a 50 USD monthly cost budget (m10)."
  }
  assert {
    condition = toset([
      for n in aws_budgets_budget.monthly.notification :
      "${n.notification_type} ${n.comparison_operator} ${n.threshold} ${n.threshold_type} ${join(",", n.subscriber_email_addresses)}"
      ]) == toset([
      "ACTUAL GREATER_THAN 80 PERCENTAGE alerts@example.com",
      "FORECASTED GREATER_THAN 100 PERCENTAGE alerts@example.com",
    ])
    error_message = "The budget must email alert_email at 80% actual and 100% forecast (m10)."
  }
}

# m9, m11-m13: the bucket can't be made public; the disks are encrypted; logs are kept 14 days.
run "storage_locked_down" {
  command = apply

  assert {
    condition = (
      aws_s3_bucket_public_access_block.data.bucket == aws_s3_bucket.data.id
      && aws_s3_bucket_public_access_block.data.block_public_acls
      && aws_s3_bucket_public_access_block.data.block_public_policy
      && aws_s3_bucket_public_access_block.data.ignore_public_acls
      && aws_s3_bucket_public_access_block.data.restrict_public_buckets
    )
    error_message = "All 4 public-access blocks must be on for the bucket (m13)."
  }
  assert {
    condition     = aws_db_instance.main.storage_encrypted
    error_message = "RDS storage must be encrypted (m11)."
  }
  assert {
    condition     = aws_instance.server.root_block_device[0].encrypted
    error_message = "The server's root volume must be encrypted (m12)."
  }
  assert {
    condition     = aws_cloudwatch_log_group.app.retention_in_days == 14
    error_message = "Logs must be kept 14 days (m9)."
  }
}

# m7 and the names table: exactly these 5 encrypted parameters.
run "ssm_names" {
  command = plan

  assert {
    condition = toset(concat(
      [aws_ssm_parameter.database_url.name],
      [for p in aws_ssm_parameter.api_key : p.name],
      [aws_ssm_parameter.langfuse_base_url.name],
      )) == toset([
      "/orgknow/DATABASE_URL",
      "/orgknow/ANTHROPIC_API_KEY",
      "/orgknow/VOYAGE_API_KEY",
      "/orgknow/LANGFUSE_PUBLIC_KEY",
      "/orgknow/LANGFUSE_SECRET_KEY",
      "/orgknow/LANGFUSE_BASE_URL",
    ])
    error_message = "The SSM parameter names must be the names table's 6."
  }
  assert {
    condition = alltrue(concat(
      [aws_ssm_parameter.database_url.type == "SecureString"],
      [for p in aws_ssm_parameter.api_key : p.type == "SecureString"],
    ))
    error_message = "Every secret must be a SecureString (m7)."
  }
  assert {
    condition     = aws_ssm_parameter.langfuse_base_url.type == "String"
    error_message = "The Langfuse host is a plain setting, not a secret (PR review, 2026-10-15)."
  }
}
