variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
}

variable "availability_zones" {
  description = "List of two AZs to spread subnets across"
  type        = list(string)
}

variable "cluster_name" {
  description = "EKS cluster name — used to tag subnets for EKS subnet discovery"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "project" {
  description = "Project name"
  type        = string
}
