variable "project_id" {
  description = "Project to enable the APIs in."
  type        = string
}

variable "services" {
  description = "API service names to enable, such as bigquery.googleapis.com."
  type        = list(string)
}
