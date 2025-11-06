provider "aws" {
  region  = "us-east-2"
  profile = "automate-deployment"
}

# TODO: set up private VPC? (need NAT gateway)
# TODO: better name (default_vpc)
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}
