# ── Chaos Experiments Table ───────────────────────────────────────────────────

resource "aws_dynamodb_table" "chaos_experiments" {
  name         = "chaos-experiments"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "experiment_id"
  range_key    = "created_at"

  attribute {
    name = "experiment_id"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  tags = {
    Name = "chaos-experiments"
  }
}

# ── Terraform State Lock Table ────────────────────────────────────────────────
# Required by the S3 backend to prevent concurrent state modifications.

resource "aws_dynamodb_table" "terraform_lock" {
  name         = "terraform-state-lock"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }

  tags = {
    Name = "terraform-state-lock"
  }
}
