project_id         = "packaging-ops-agent-dev"
environment        = "dev"
region             = "us-central1"
bigquery_location  = "US"
billing_account_id = "01B7CD-00412F-D365AB"
budget_amount_usd  = 25

# Dev can be torn down and rebuilt at any time, data included.
destroyable = true

# GitHub Actions authenticates through Workload Identity Federation. The IDs
# come from `gh api repos/justfetz/packaging-ops-agent` (.id and .owner.id).
github_repository          = "justfetz/packaging-ops-agent"
github_repository_id       = "1440268397"
github_repository_owner_id = "12513697"
