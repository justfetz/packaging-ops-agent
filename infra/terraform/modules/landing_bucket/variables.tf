variable "project_id" {
  description = "Project that owns the bucket."
  type        = string
}

variable "name" {
  description = "Globally unique bucket name."
  type        = string
}

variable "location" {
  description = "Bucket location, a region such as us-central1."
  type        = string
}

variable "force_destroy" {
  description = "Delete all objects when the bucket is destroyed. True in dev, false in prod."
  type        = bool
  default     = false
}

variable "noncurrent_versions_to_keep" {
  description = "How many noncurrent versions of each object to retain before older ones are deleted."
  type        = number
  default     = 5
}

variable "labels" {
  description = "Labels applied to the bucket."
  type        = map(string)
  default     = {}
}
