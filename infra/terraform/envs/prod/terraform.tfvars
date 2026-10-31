# The prod project does not exist yet. Create it and link billing the same way
# as dev (issue #3), run `make bootstrap ENV=prod`, then `make plan ENV=prod`.
# `terraform apply` to prod needs the owner's explicit go-ahead.
project_id         = "packaging-ops-agent-prod"
environment        = "prod"
region             = "us-central1"
bigquery_location  = "US"
billing_account_id = "01B7CD-00412F-D365AB"
budget_amount_usd  = 25

# Prod keeps its data. A destroy fails if a bucket or dataset is not empty.
destroyable = false
