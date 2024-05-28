# AWS CBS 2.0 Deployment Instructions

---

## For Us

### Add partner to DynamoDB table
1. Navigate to the [Partner Onboarding Pipeline](https://github.com/CybercentreCanada/cbs-aws-2/actions/workflows/partner_onboarding.yml)
2. Select **Run workflow** at the top right of the page
    1. **Branch:** `production`
    2. **Action:** `Write`
    3. **CBS ID:** Partner's CBS ID
    4. **Management Account ID:** Partner's management account ID
    5. **Log Archive Account ID:** Partner's log archive account ID
    6. **Accelerator:** Partner's accelerator of choice (LZA, ASEA, or None)
    7. **Disclosure Expiry:** For disclosure use cases, enter an expiry timestamp
    8. Select **Run workflow** at the bottom right of the dialog
3. Our CI/CD CodePipeline will then be triggered to run which will create and configure the partner's destination bucket for replication

---

## For Partners

### Configure Dynamic Partitioning of VPC Flow Logs
1. Sign into your LZA root account management console
2. Navigate to the CodeCommit service
3. Select the **aws-accelerator-config** repository
4. Select the **dynamic-partitioning** folder
5. Select the **log-filters.json** file
6. Select **Edit** and replace the file contents with the following:
```json
[
  { "logGroupPattern": "/AWSAccelerator/MAD", "s3Prefix": "managed-ad" },
  { "logGroupPattern": "/AWSAccelerator/rql", "s3Prefix": "rql" },
  { "logGroupPattern": "/AWSAccelerator-SecurityHub", "s3Prefix": "security-hub" },
  { "logGroupPattern": "AwsAcceleratorFirewallFlowLogGroup", "s3Prefix": "nfw" },
  { "logGroupPattern": "aws-accelerator-sessionmanager-logs", "s3Prefix": "ssm" },
  { "logGroupPattern": "VpcFlowLogsGroup", "s3Prefix": "vpcflowlogs"}
]
```
