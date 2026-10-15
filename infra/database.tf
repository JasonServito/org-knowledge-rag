# The database (m11, ADR-014 D3, D5): Postgres 18 on RDS, in the private subnets, loaded once from
# a dump of the laptop's database (runbook step 5).

# Letters and digits only, so the password can sit in DATABASE_URL without URL-escaping (m7).
# It is kept in the local state file, which is why that file is gitignored (D6).
resource "random_password" "db" {
  length  = 32
  special = false
}

resource "aws_db_instance" "main" {
  identifier     = "orgknow"
  engine         = "postgres"
  engine_version = "18"
  instance_class = "db.t4g.micro"

  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "orgknow"
  username = "orgknow"
  password = random_password.db.result
  port     = 5432

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]
  publicly_accessible    = false
  multi_az               = false

  # Teardown removes it outright (D7): the data reloads from the dump, so no final snapshot, no
  # deletion protection, and 1 day of backups.
  backup_retention_period = 1
  skip_final_snapshot     = true
  deletion_protection     = false
}
