# Remote state in a GCS bucket. A backend block cannot read variables, so the
# bucket name lives in backend.tfvars next to this file and `make plan` passes
# it with `-backend-config=backend.tfvars`. The bucket is created
# once by `make bootstrap ENV=<env>` because Terraform cannot create the bucket
# that holds its own state.
terraform {
  backend "gcs" {}
}
