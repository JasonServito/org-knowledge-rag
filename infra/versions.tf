# Terraform and its providers (S15-T4, ADR-014). Each provider may move only within one minor
# version; the committed lock file (.terraform.lock.hcl) pins the exact build and its hashes, which
# `terraform init` checks (m8). State stays on the laptop, gitignored: no backend block (D6).
terraform {
  required_version = ">= 1.14"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9.0"
    }
  }
}

# One region for everything (m1). Every resource gets the project's tag, so the console's resource
# and cost views can filter on it.
provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project = "orgknow"
    }
  }
}
