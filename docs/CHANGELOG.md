# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

#### Types of changes:

><span style="color:grey"><b>Added</b></span> for new features.<br>
><span style="color:grey"><b>Changed</b></span> for changes in existing functionality.<br>
><span style="color:grey"><b>Deprecated</b></span> for soon-to-be removed features.<br>
><span style="color:grey"><b>Removed</b></span> for now removed features.<br>
><span style="color:grey"><b>Fixed</b></span> for any bug fixes.<br>
><span style="color:grey"><b>Security</b></span> in case of vulnerabilities.

---

## [2.3.12] - 2024-05-14

### Added

- Support for LZA+CT CBS installations

### Changed

- Transport and SQS Router Lambdas read partners directly from inventory table rather than as an environment variable

### Removed

- Transport and SQS Router Lambdas `PARTNERS` environment variable
- Support for CloudTrail Digest logs
- Stamping of 2.0 SQS message metadata with partner organization ID

## [2.3.11] - 2024-05-07

### Added

- IAMRA GitHub composite action
- CBS Common GitHub action & permissions for DevOps role

### Changed

- Transport Lambda log field `CbsId` to `CbsSensorId`

### Fixed

- SQS Router datetime parsing

## [2.3.10] - 2024-05-06

### Added

- CBS installer Control Tower support
- CBS core Lambda Layer

### Changed

- IAM Metadata format
- Repo structure

### Removed

- CBS constants Lambda Layer

### Fixed

- CBS installer batch replication jobs

## [2.3.9] - 2024-04-16

### Added

- IAM Metadata Lambda
- Enriched SSO Metadata permission sets with applicable policies
- Replication rule wizard is now skippable

### Changed

- Assume role to session-based

### Fixed

- VPC config KeyError and ConstructorError

## [2.3.8] - 2024-04-09

### Fixed

- Use sessions instead of clients for installer
- Various installer bugs
- Add `AWSControlTowerExecution` back to list of super admin roles

## [2.3.7] - 2024-04-05

### Changed

- Sort CloudWatch Alarms panel by last updated

### Fixed

- Remove `AWSControlTowerExecution` from list of super admin roles

## [2.3.6] - 2024-04-04

### Added

- CloudWatch Alarms Grafana data source & panel
- Remove expired disclosure partners and empty file events using EventBridge rule

## [2.3.5] - 2024-03-27

### Added

- Allow partner accelerator to be `None`

## [2.3.4] - 2024-03-20

### Fixed

- Partner bucket policy condition
- Core workloads metric filter pattern

## [2.3.3] - 2024-03-11

### Changed

- Removed CBS Global Reader Roles feature flag from installer

### Fixed

- CBS installer batch replication bug
- CBS event VPC flow log bugs

## [2.3.2] - 2024-03-06

### Changed

- SSO metadata permission sets grouped by principal

### Fixed

- YAML ScannerError on VPC flow log workloads

## [2.3.1] - 2024-02-28

### Added

- S3 batch replication option during installation
- Automatically enable CloudFormation StackSets Trusted Access prior to global reader install
- Deny assume role action on partner global readers after disclosure expiry

### Fixed

- CBS metadata EventBridge rule
- CBS installer checks for existing CBS replication rules based on destination bucket rather than ID

## [2.3.0] - 2024-02-22

### Added

- CBS Global Reader Role Terraform
- SSO Metadata Lambda
- State Machine to orchestrate SSO Metadata Lambda invocations across partners with global reader
- CloudWatch Alarms for 1.0 partners
- Alarm-specific playbooks for Opsgenie integration

### Changed

- Migrated Azure DevOps partner onboarding pipeline to GitHub Actions
- Migrated CodePipeline linting to GitHub Actions

### Removed

- Unused code

## [2.2.2] - 2024-01-29

### Added

- IAM Roles Anywhere authentication for Azure DevOps pipeline & replication rule validator GitHub Action
- Per-partner filtering for 1.0 partners on dashboard

### Changed

- Replication rule validator uses remote config bucket instead of CLI args

## [2.2.1] - 2024-01-24

### Added

- IAM Roles Anywhere authentication for DevOps role - removes long-term user access keys
- Per-partner filtering for 2.0 partners on dashboard

### Fixed

- CBS installer existing replication role policy bug

## [2.2.0] - 2024-01-16

### Added

- Grafana dashboarding

### Fixed

- CBS installer V1 replication configuration bug

## [2.1.8] - 2024-01-10

### Added

- Unknown workload metric
- CBS installer tests
- CBS disclosure tests

### Fixed

- Various CBS installer bugs
- Lambda imports are now all relative. No more absolute imports to accommodate pytest

## [2.1.7] - 2024-01-03

### Added

- CBS installer script
- CloudWatch Alarms suppression for alarms that require > 5 mins. of metrics

### Changed

- DLQ Triage refactor

### Removed

- S3 Object Lambda
- `cloudwatch.rsysLogs` workload support

## [2.1.6-a] - 2023-12-13

### Fixed

- DLQ Triage bug

## [2.1.6] - 2023-12-11

### Added

- Improved test coverage

### Changed

- Optimized `PARTNERS` environment variable for Transport Lambda (cuts size by nearly 50%)
- Replication rule validator build to Python 3.9 to support upgraded Python runtime on CloudShell

## [2.1.5] - 2023-12-04

### Added

- Org ID to SQS messages

### Fixed

- Replication rule validator bugs

## [2.1.4] - 2023-11-20

### Added

- DLQ Triage tests

### Changed

- Transport and SQS Router Lambda timeouts from 3 seconds to 4 seconds
- Indigestion alarm's metric period from 1 minute to 5 minutes

### Fixed

- BatchWriteItem API's limitation of 25 entries

## [2.1.3] - 2023-10-31

### Added

- CBS disclosure use case
- Support for both VPC flow log sources
- Support for S3 access logs (LZA only)

### Fixed

- Known workloads appearing in unknown workloads table

## [2.1.2] - 2023-10-24

### Added

- CloudWatch Alarms toggle based on partner deployment status
- CloudWatch Alarms notification formatter Lambda
- Dynamically read a partner's configured VPC flow log fields from their accelerator metadata
- Common functions Lambda Layer

### Changed

- Transport Lambda environment variables are now zlib-compressed

### Removed
- Heartbeat Lambda

### Fixed

- Config logs regex
- Replication rule validator not checking role policies properly

## [2.1.1] - 2023-10-03

### Added

- Replication rule validator and build workflow

### Changed

- Refactored CloudWatch alarms, DLQ triage lambda & heartbeat lambda into respective nested stacks
- Tag VPC flow logs as `cloudwatch.vpcFlowLogs` instead of `vpcFlowLogs` to indicate to 4A of CloudWatch wrapper

### Fixed

- DLQ triage erroring on empty string after object key sanitization
- S3 access logs triaging
- Metadata objects being tagged as ELB logs

## [2.1.0] - 2023-08-31

### Added

- CloudWatch Alarm to alert on a dropoff of replication to partner buckets
- CloudWatch Alarms to alert on missing workloads per partner
- Validate CBS config using Pydantic

### Changed

- Keep full config in SSM parameter store to protect sensitive values

### Fixed

- CDK tests
- Database pipeline doesn't strip leading zeroes from account ID input anymore

## [2.0.2] - 2023-08-17

### Added

- Custom resource for storing partner bucket name and key ARN in inventory table
- SQS router will check partner buckets for whether replication has begun when deciding whether to route messages

### Changed

- Removed CloudTrail Insight workload support
- Synth CodeBuild image to `LinuxBuildImage.STANDARD_7_0` to fix node deprecation notice

## [2.0.1] - 2023-08-02

### Added

- Remove organization ID from object key during DLQ triage

### Changed

- Improved deployment model to use per environment configuration files rather than `cdk.json` context variables
- Upgraded Lambda runtimes to Python 3.11

### Fixed

- SQS router log message for agents < v1.8.2
- DynamoDB DevOps script CodePipeline naming convention

## [2.0.0] - 2023-07-25

### Added

- SQS message router lambda to handle the forwarding of 1.x partners' SQS messages to the 2.x SQS
- DLQ message triager lambda to keep a record of unknown workloads and to notify stakeholders
- S3 object lambda to handle conversion of logs to [parquet](https://github.com/apache/parquet-format#readme) format on GET requests to partner buckets

### Changed

- CI/CD CodePipeline to pull directly from our GitHub repo instead of using Azure DevOps pipelines to manage CI/CD
- S3 bucket replication for cross-account log transport instead of S3 event notifications
- EventBridge instead of SNS to trigger transport lambda for processing of log object events

### Removed

- SNS subscribe lambda
