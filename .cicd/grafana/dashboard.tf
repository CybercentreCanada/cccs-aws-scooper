locals {
  deployment_env = var.deployment.branch == "staging" ? "stage" : "prod"
  template       = templatefile("./dashboard/model.json", { account_id = var.deployment.account_id, env = local.deployment_env })
}

resource "grafana_data_source" "cloudwatch" {
  type = "cloudwatch"
  name = "CloudWatch"

  json_data_encoded = jsonencode({
    authType                = "keys"
    assumeRoleArn           = "arn:aws:iam::${var.deployment.account_id}:role/CBS-GrafanaMonitoringRole-${local.deployment_env}-ca-central-1"
    customMetricsNamespaces = "CBS"
    defaultRegion           = "ca-central-1"
  })

  secure_json_data_encoded = jsonencode({
    accessKey = var.cloudwatch_auth.access_key
    secretKey = var.cloudwatch_auth.secret_key
  })
}

resource "grafana_data_source" "cloudwatch_alarms" {
  type = "computest-cloudwatchalarm-datasource"
  name = "CloudWatch Alarms"

  json_data_encoded = jsonencode({
    authType                = "keys"
    assumeRoleArn           = "arn:aws:iam::${var.deployment.account_id}:role/CBS-GrafanaMonitoringRole-${local.deployment_env}-ca-central-1"
    defaultRegion           = "ca-central-1"
  })

  secure_json_data_encoded = jsonencode({
    accessKey = var.cloudwatch_auth.access_key
    secretKey = var.cloudwatch_auth.secret_key
  })
}

resource "grafana_folder" "aws" {
  title = "AWS"
}

resource "grafana_dashboard" "aws" {
  depends_on  = [
    grafana_data_source.cloudwatch,
    grafana_data_source.cloudwatch_alarms,
  ]
  folder      = grafana_folder.aws.uid
  message     = "${var.git_commit_url}"
  overwrite   = true
  config_json = local.template
}
