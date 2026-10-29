# Storage (m13): the bucket for the database dump and the corpus archive, and the image registry.
# Both are removed by `terraform destroy` even when not empty (D7, c5).

resource "aws_s3_bucket" "data" {
  bucket        = "orgknow-${data.aws_caller_identity.current.account_id}-${var.region}"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data" {
  bucket = aws_s3_bucket.data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_ecr_repository" "app" {
  name = "orgknow"
  # Without it, `destroy` stops on a repository that still holds images (c5).
  force_delete = true

  # ECR scans each pushed image for known vulnerabilities; it reports only (security review 5.5).
  image_scanning_configuration {
    scan_on_push = true
  }
}

# Keep the last 3 images: enough to roll back, and storage stays at a few GB.
resource "aws_ecr_lifecycle_policy" "app" {
  repository = aws_ecr_repository.app.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep the last 3 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 3
      }
      action = { type = "expire" }
    }]
  })
}
