# The inputs (the S15 plan's names table). alert_email and langfuse_base_url have no default:
# set them in terraform.tfvars (gitignored; copy terraform.tfvars.example).

variable "region" {
  description = "The AWS region for every resource (m1)."
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "The server's EC2 type (ADR-014 D2: t3a.medium, 2 vCPU, 4 GiB; the reranker needs ~1.6 GiB)."
  type        = string
  default     = "t3a.medium"
}

variable "alert_email" {
  description = "Where the budget and the alarms send email (m9, m10)."
  type        = string
}

variable "langfuse_base_url" {
  description = "The Langfuse host the server's traces go to: the same LANGFUSE_BASE_URL as the laptop's .env (the app's default is the EU host)."
  type        = string
}

variable "budget_usd" {
  description = "The monthly cost budget in US dollars (m10, ADR-014 D7)."
  type        = number
  default     = 50
}
