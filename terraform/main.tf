terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
    null = {
      source  = "hashicorp/null"
      version = "~> 3.2"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = var.tags
  }
}

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  src_dir   = abspath("${path.module}/../src")
  build_dir = abspath("${path.module}/.build")
  zip_path  = abspath("${path.module}/.build/lambda.zip")

  # Rebuild the package whenever any source or requirements file changes.
  src_hash = sha256(join("", [
    for f in sort(fileset(local.src_dir, "**/*.{py,txt}"))
    : filesha256("${local.src_dir}/${f}")
  ]))
}
