# What the runbook needs after `apply` (`terraform -chdir=infra output`).

output "ecr_repository_url" {
  description = "Where `docker push` sends the image (tag: the git short SHA)."
  value       = aws_ecr_repository.app.repository_url
}

output "bucket_name" {
  description = "The bucket for orgknow.dump and corpus_cache.tar.gz."
  value       = aws_s3_bucket.data.bucket
}

output "instance_id" {
  description = "The server, for Session Manager (shell and port forwarding)."
  value       = aws_instance.server.id
}

output "rds_endpoint" {
  description = "The database's host name, without the port (5432)."
  value       = aws_db_instance.main.address
}
