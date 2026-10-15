# The app's secrets (m7, ADR-014 D6): encrypted SSM parameters named /orgknow/<ENV_VAR>, which the
# deploy script writes to the server's env file.

# Written by Terraform from the generated password and the database's host name (`address`: the
# host alone; `endpoint` would add the port a second time).
resource "aws_ssm_parameter" "database_url" {
  name  = "/orgknow/DATABASE_URL"
  type  = "SecureString"
  value = "postgresql://${aws_db_instance.main.username}:${random_password.db.result}@${aws_db_instance.main.address}:${aws_db_instance.main.port}/${aws_db_instance.main.db_name}?sslmode=require"
}

# Set by the developer with `aws ssm put-parameter --overwrite` (runbook step 3). Terraform creates
# each name with a placeholder and never changes the value after (c4), so the names are in code
# and the real keys never are.
resource "aws_ssm_parameter" "api_key" {
  for_each = toset(["ANTHROPIC_API_KEY", "VOYAGE_API_KEY", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"])

  name  = "/orgknow/${each.key}"
  type  = "SecureString"
  value = "set-me"

  lifecycle {
    ignore_changes = [value]
  }
}

# The one setting the server needs beyond the defaults (PR review, 2026-10-15): the Langfuse
# region. Not a secret, so a plain String; the deploy script reads it with the others.
resource "aws_ssm_parameter" "langfuse_base_url" {
  name  = "/orgknow/LANGFUSE_BASE_URL"
  type  = "String"
  value = var.langfuse_base_url
}
