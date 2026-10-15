# Logs, alarms and the budget (m9, m10, ADR-014 D7). Every alert is an email to alert_email.

# The containers' logs (Docker's awslogs driver; streams api and worker), kept 14 days.
resource "aws_cloudwatch_log_group" "app" {
  name              = "/orgknow"
  retention_in_days = 14
}

# The alarms' email. AWS sends a confirmation email first: click its link (runbook step 2).
resource "aws_sns_topic" "alerts" {
  name = "orgknow-alerts"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# The server failed a status check (its own or AWS's hardware) in a 5-minute period.
resource "aws_cloudwatch_metric_alarm" "server_status" {
  alarm_name          = "orgknow-server-status-check"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed"
  dimensions          = { InstanceId = aws_instance.server.id }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# The database has under 2 GiB of its 20 GB free.
resource "aws_cloudwatch_metric_alarm" "db_free_storage" {
  alarm_name          = "orgknow-db-free-storage"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.main.identifier }
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "LessThanThreshold"
  threshold           = 2 * 1024 * 1024 * 1024 # bytes
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# The whole account's monthly cost: email at 80% of the budget spent, and when the month's
# forecast passes 100%.
resource "aws_budgets_budget" "monthly" {
  name         = "orgknow-monthly"
  budget_type  = "COST"
  limit_amount = tostring(var.budget_usd)
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    notification_type          = "ACTUAL"
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    notification_type          = "FORECASTED"
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    subscriber_email_addresses = [var.alert_email]
  }
}
