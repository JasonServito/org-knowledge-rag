# The network (ADR-014 D3): an own VPC with 1 public subnet for the server and 2 private subnets for
# the database. Every rule and route is written inline in its group or table (no separate rule or
# route resources), so the tests see all of them (tests/rules.tftest.hcl, "rules_are_inline").

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
}

# The server's subnet. Its only way out is the internet gateway: the server's public IPv4 is for
# outbound calls (Anthropic, Voyage, Langfuse, ECR, SSM, S3); no NAT gateway (D7).
resource "aws_subnet" "public" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "${var.region}a"
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# The database's subnets: 2 zones, because an RDS subnet group needs 2 even for a single-zone
# database.
resource "aws_subnet" "private_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.11.0/24"
  availability_zone = "${var.region}a"
}

resource "aws_subnet" "private_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.12.0/24"
  availability_zone = "${var.region}b"
}

# No route to the internet: only the implicit local route inside the VPC. `route = []` also makes
# Terraform remove any route added outside it at the next apply.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id
  route  = []
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private.id
}

resource "aws_db_subnet_group" "main" {
  name       = "orgknow"
  subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
}

# The server: no inbound rule at all (D1; reached through Session Manager, which needs no open
# port), and every outbound connection allowed (c3). `ingress = []` also makes Terraform remove any
# inbound rule added outside it at the next apply.
resource "aws_security_group" "server" {
  name        = "orgknow-server"
  description = "orgknow server: no inbound, all outbound"
  vpc_id      = aws_vpc.main.id
  ingress     = []

  egress {
    description = "All outbound (c3)"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# The database: Postgres's port, from the server's group only (D3). No outbound rule: Terraform
# removes AWS's default allow-all one, and the database only answers connections.
resource "aws_security_group" "db" {
  name        = "orgknow-db"
  description = "orgknow database: Postgres from the server only"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from the server"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.server.id]
  }
}
