# infra/terraform/

Terraform for every GCP resource. Shared modules plus two roots, `envs/dev` and `envs/prod`, each with its own GCS state backend and tfvars.

Filled in **M0.3**. Rules: `terraform plan` runs freely; `terraform apply` to prod needs the owner's go-ahead; dev can be destroyed and rebuilt at any time; no long-lived keys in the repo.
