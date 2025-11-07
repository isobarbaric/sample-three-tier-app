resource "aws_ecs_cluster" "main" {
  name = var.cluster_name
  
  tags = {
    Name = var.cluster_name
  }
}

# TODO: set up log group
resource "aws_ecs_task_definition" "frontend" {
  family                   = "three-tier-app-frontend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name  = "frontend"
    image = "${var.ecr_registry}/frontend:latest"
    
    portMappings = [{
      containerPort = 80
      protocol      = "tcp"
    }]

    environment = [{
      name  = "BACKEND_URL"
      value = "http://backend:8000"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/three-tier-app-frontend"
        "awslogs-region"        = "us-east-2"
        "awslogs-stream-prefix" = "ecs"
        "awslogs-create-group"  = "true"
      }
    }

    essential = true
  }])

  tags = {
    Name = "three-tier-app-frontend-task"
  }
}

resource "aws_ecs_service" "frontend" {
  name            = "three-tier-app-frontend-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.frontend.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.frontend.id]
    assign_public_ip = true
  }
  
  tags = {
    Name = "three-tier-app-frontend-service"
  }
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "three-tier-app-backend"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_task_execution.arn

  container_definitions = jsonencode([{
    name  = "backend"
    image = "${var.ecr_registry}/backend:latest"
    
    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    environment = [{
      name  = "DATABASE_URL"
      value = "sqlite+aiosqlite:///./todos.db"
    }]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/three-tier-app-backend"
        "awslogs-region"        = "us-east-2"
        "awslogs-stream-prefix" = "ecs"
        "awslogs-create-group"  = "true"
      }
    }

    essential = true
  }])

  tags = {
    Name = "three-tier-app-backend-task"
  }
}

resource "aws_ecs_service" "backend" {
  name            = "three-tier-app-backend-service"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  
  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.backend.id]
    assign_public_ip = true
  }
  
  tags = {
    Name = "three-tier-app-backend-service"
  }
}
