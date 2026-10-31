variable "project_id" {
  description = "Project that owns the datasets."
  type        = string
}

variable "datasets" {
  description = "Dataset IDs mapped to their descriptions."
  type        = map(string)
}

variable "location" {
  description = "Dataset location. The US multi-region keeps BigQuery and Vertex AI in one geography."
  type        = string
  default     = "US"
}

variable "delete_contents_on_destroy" {
  description = "Drop tables when a dataset is destroyed. True in dev, false in prod."
  type        = bool
  default     = false
}

variable "labels" {
  description = "Labels applied to every dataset."
  type        = map(string)
  default     = {}
}
