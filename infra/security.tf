
resource "aws_security_group" "frontend" {
  name        = "three-tier-app-frontend-sg"
  description = "Security group for frontend service"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "Allow HTTP traffic from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "three-tier-app-frontend-sg"
  }
}

resource "aws_security_group" "backend" {
  name        = "three-tier-app-backend-sg"
  description = "Security group for backend service"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description     = "Allow traffic from frontend"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.frontend.id]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "three-tier-app-backend-sg"
  }
}