# Passed to `terraform init -backend-config=backend.tfvars` by the Makefile.
# No prefix on purpose: one bucket per environment, and an object name with no
# slash in it is the one shape every client, including a proxied Claude Code
# session, can read back by name.
bucket = "packaging-ops-agent-prod-tfstate"
