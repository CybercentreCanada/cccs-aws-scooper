from string import Template

# Partner table attribute names
MGMT_ACCOUNT_ID = "mgmt-account-id"
ACCOUNT_ID = "account-id"
CBS_ID = "cbs-id"
ORG_ID = "org-id"
ACCELERATOR = "accelerator"
BUCKET_NAME = "bucket-name"
KMS_ARN = "kms-arn"
DEPLOYED = "deployed"
VPC_CUSTOM_FIELDS = "vpc-custom-fields"
DISCLOSURE_EXPIRY = "disclosure-expiry"
ALARM_TYPE = "alarm-type"
SUPPRESSION_EXPIRY = "suppression-expiry"

# Environment variable names
PARTNERS = "PARTNERS"

# DynamoDB constants
INVENTORY_TABLE_NAME = "InventoryTable"
DISCLOSURE_EXPIRY_FORMAT = "%Y-%m-%dT%H:%M:%S"

CBS_GLOBAL_READER_ROLE_TEMPLATE = Template(
    "arn:aws:iam::$account:role/cbs-global-reader"
)

UNSUPPORTED_WORKLOADS = (
    "/CloudTrail-Digest/",
    "/CloudTrail-Insight/",
    "ConfigWritabilityCheckFile",
    "Cost-and-Usage-Report",
    "ELBAccessLogTestFile",
    "/SSM/",
)

CBS_METADATA_OBJECT_KEY = "cbs-metadata"

LOG_TYPE_REGEX_TO_WORKLOAD_MAP = {
    "/cloudtrail/": "cloudtrailLogs",
    r"[\d]{12}/config/": "configLogs",
    "cloudwatchlogs/vpcflowlogs/": "cloudwatch.vpcFlowLogs",
    r"[\d]{12}/vpcflowlogs/": "vpcFlowLogs",
    "cloudwatchlogs/managed-ad": "cloudwatch.managedADLogs",
    "cloudwatchlogs/nfw": "cloudwatch.nfwLogs",
    "cloudwatchlogs/rql": "cloudwatch.rqlLogs",
    "cloudwatchlogs/security-hub": "cloudwatch.securityHubLogs",
    "cloudwatchlogs/ssm": "cloudwatch.ssm",
    "cloudwatchlogs/transport-lambda": "cloudwatch.transportLambdaLogs",
    "cloudwatchlogs": "cloudwatchLogs",
    r"[\d]{12}/elb-": "elbLogsV2",
    "/guardduty/": "guardDutyLogs",
    "ssm-inventory/aws:application": "ssmInventory.application",
    "ssm-inventory/aws:awscomponent": "ssmInventory.awsComponent",
    "ssm-inventory/aws:billinginfo": "ssmInventory.billingInfo",
    "ssm-inventory/aws:complianceitem": "ssmInventory.complianceItem",
    "ssm-inventory/aws:compliancesummary": "ssmInventory.complianceSummary",
    "ssm-inventory/aws:instancedetailedinformation": "ssmInventory.instancedetailedInformation",
    "ssm-inventory/aws:instanceinformation": "ssmInventory.instanceInformation",
    "ssm-inventory/aws:network": "ssmInventory.network",
    "ssm-inventory/aws:service": "ssmInventory.service",
    "ssm-inventory/aws:tag": "ssmInventory.tag",
    "ssm-inventory/aws:windowsrole": "ssmInventory.windowsRole",
    "ssm-inventory/aws:windowsupdate": "ssmInventory.windowsUpdate",
    f"/{CBS_METADATA_OBJECT_KEY}/iam.json": "metadata.iam",
    f"/{CBS_METADATA_OBJECT_KEY}/sso.json": "metadata.sso",
}

LZA_LOG_TYPE_REGEX_TO_WORKLOAD_MAP = LOG_TYPE_REGEX_TO_WORKLOAD_MAP | {
    r"\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}-[a-z0-9]{16}$": "s3AccessLogs",
    "config/global-config.yaml": "lzaMetadata.configFile",
    "config/service-control-policies/": "lzaMetadata.scp",
    "metadata.json": "lzaMetadata",
}

ASEA_LOG_TYPE_REGEX_TO_WORKLOAD_MAP = LOG_TYPE_REGEX_TO_WORKLOAD_MAP | {
    "config/config.json": "aseaMetadata.configFile",
    "config/scp/": "aseaMetadata.scp",
    "metadata.json": "aseaMetadata",
}

DEFAULT_VPC_FLOW_LOG_FIELDS = (
    "version",
    "account-id",
    "interface-id",
    "srcaddr",
    "dstaddr",
    "srcport",
    "dstport",
    "protocol",
    "packets",
    "bytes",
    "start",
    "end",
    "action",
    "log-status",
    "vpc-id",
    "subnet-id",
    "instance-id",
    "tcp-flags",
    "type",
    "pkt-srcaddr",
    "pkt-dstaddr",
    "region",
    "az-id",
    "pkt-src-aws-service",
    "pkt-dst-aws-service",
    "flow-direction",
    "traffic-path",
)
