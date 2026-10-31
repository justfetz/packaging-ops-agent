# Enables the Google Cloud APIs an environment needs. Enabling an API is free
# and idempotent. We never disable APIs on destroy: disabling one can take down
# services that other, still-present resources depend on, and a rebuilt dev
# project would only have to turn them back on.
resource "google_project_service" "this" {
  for_each = toset(var.services)

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
