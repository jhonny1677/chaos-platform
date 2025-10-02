terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
  }

  # BOOTSTRAP NOTE:
  # On the very first run, comment out this entire backend block and run:
  #   terraform init && terraform apply -target=module.s3
  # Once the S3 bucket exists, uncomment this block, replace ACCOUNT_ID below,
  # then run: terraform init -migrate-state
  backend "s3" {
    bucket         = "chaos-platform-tfstate-ACCOUNT_ID"
    key            = "global/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
