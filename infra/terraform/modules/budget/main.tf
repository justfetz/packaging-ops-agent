# A monthly budget on the billing account, scoped to this project. Budgets are
# billing-account resources, so they survive a project rebuild, and whoever
# runs Terraform needs Billing Account Costs Manager on the billing account.
#
# Spend is measured before credits so a free-trial credit cannot hide real
# usage until the day it runs out.
resource "google_billing_budget" "this" {
  billing_account = var.billing_account_id
  display_name    = var.display_name

  budget_filter {
    projects               = ["projects/${var.project_number}"]
    calendar_period        = "MONTH"
    credit_types_treatment = "EXCLUDE_ALL_CREDITS"
  }

  amount {
    specified_amount {
      currency_code = "USD"
      units         = tostring(var.amount_usd)
    }
  }

  dynamic "threshold_rules" {
    for_each = var.threshold_percents
    content {
      threshold_percent = threshold_rules.value
      spend_basis       = "CURRENT_SPEND"
    }
  }

  # No all_updates_rule: with none set, threshold emails go to the billing
  # account's Billing Account Administrators and Users, which is the owner.
  # The provider requires a Monitoring channel or Pub/Sub topic to set one.
}
