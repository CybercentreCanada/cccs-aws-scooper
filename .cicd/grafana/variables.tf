variable "grafana_auth" {
  type = object({
    url     = string
    api_key = string
  })
  sensitive = true
}

variable "cloudwatch_auth" {
  type = object({
    access_key = string
    secret_key = string
  })
  sensitive = true
}

variable "deployment" {
  type = object({
    account_id = string
    branch     = string
  })
}

variable "git_commit_url" {
  type = string
}
