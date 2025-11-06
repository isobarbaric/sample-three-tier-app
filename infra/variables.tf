# TODO: add these ports in
# variable "frontend_port" {
#   type        = number
#   default     = 3000
# }

# variable "backend_port" {
#   type        = number
#   default     = 8000
# }

# variable "aws_region" {
#   description = "AWS region for resources"
#   type        = string
#   default     = "us-east-2"
# }

variable "ecr_registry" {
  description = "ECR registry URL"
  type        = string
  default     = "358262661502.dkr.ecr.us-east-2.amazonaws.com"
}

variable "cluster_name" {
  description = "Name of the ECS cluster"
  type        = string
  default     = "three-tier-cluster"
}

# variable "app_name" {
#   description = "Application name for resource naming"
#   type        = string
#   default     = "three-tier-app"
# }