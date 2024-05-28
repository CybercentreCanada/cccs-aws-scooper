locals {
  cbs_global_reader_role_template = yamldecode(
    templatefile(
      "./cbs_global_reader.yaml",
      { cccs_role_arn = var.cccs_role_arn },
    )
  )
}

data "aws_organizations_organization" "org" {}

resource "aws_cloudformation_stack_set" "cbs_global_reader_roles" {
  name        = "CBS-Global-Reader-Roles"
  description = "Deploys a role to every account within the organization with ReadOnlyAccess for CBS to assume"

  permission_model = "SERVICE_MANAGED"
  capabilities     = ["CAPABILITY_NAMED_IAM"]
  auto_deployment {
    enabled                          = true
    retain_stacks_on_account_removal = false
  }
  managed_execution {
    active = true
  }

  template_body = jsonencode(local.cbs_global_reader_role_template)
  tags = {
    Owner = "CBS"
  }
}

resource "aws_cloudformation_stack_set_instance" "cbs_global_reader_role" {
  deployment_targets {
    organizational_unit_ids = [data.aws_organizations_organization.org.roots[0].id]
  }

  region         = "ca-central-1"
  stack_set_name = aws_cloudformation_stack_set.cbs_global_reader_roles.name
}

resource "aws_iam_role" "cbs_global_reader_role" {
  name        = "cbs-global-reader"
  description = "Global Reader Role for CBS"

  assume_role_policy = jsonencode(
    local.cbs_global_reader_role_template.Resources.CBSGlobalReader.Properties.AssumeRolePolicyDocument
  )
  managed_policy_arns = local.cbs_global_reader_role_template.Resources.CBSGlobalReader.Properties.ManagedPolicyArns
  tags = {
    Owner = "CBS"
  }
}
