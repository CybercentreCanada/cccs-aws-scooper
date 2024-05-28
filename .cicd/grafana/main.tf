terraform {
  required_providers {
    grafana = {
      source  = "grafana/grafana"
      version = "~> 2.8"
    }
  }
  backend "s3" {}
}

provider "grafana" {
  url  = var.grafana_auth.url
  auth = var.grafana_auth.api_key
}
