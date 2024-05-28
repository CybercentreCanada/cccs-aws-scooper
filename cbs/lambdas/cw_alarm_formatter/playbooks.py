INDIGESTION_ALARM_PLAYBOOK = """
ADS4A's AWS events processor microservice is failing to GET objects in bucket.

Potential causes:
  1. Transport Lambda isn't sending messages about given partner to the SQS for ADS4A to consume
    - Could be an issue with the Transport Lambda
    - Could indicate an issue with the partner's replication rules or accelerator configuration
  2. A lack of telemetry from the partner has triggered a false positive
  3. ADS4A's microservice is dead

Courses of action:
  1.
    - Check Transport Lambda logs for errors
    - Open an Opsgenie incident for ACE3C to action for partner reach out
  2. Monitor closely until telemetry reappears
  3. Open an Opsgenie incident for ADS4A to action
"""

REPLICATION_ALARM_PLAYBOOK = """
Partner's destination bucket hasn't had a new object in two days.

Potential causes:
  1. Partner's replication rules have been misconfigured
  2. Partner's accelerator has misconfigured logging
  3. Partner's destination bucket has been misconfigured

Courses of action:
  1, 2. Open an Opsgenie incident for ACE3C to action for partner reach out
  3. Check partner config bucket in CI/CD account for their CBS config information.
     If there are differing versions of their config, then the CDK has changed the
     partner's destination bucket configuration which will require a re-deployment
     of CBS by the partner. Open an Opsgenie incident for ACE3C to action for partner reach out
"""

CLOUDTRAIL_WORKLOAD_ALARM_PLAYBOOK = """
Partner's CloudTrail telemetry has stopped.

Potential causes:
  1. Could be a symptom of an Indigestion or Replication alarm
  2. Partner's accelerator is failing to aggregate CloudTrail logs

Courses of action:
  1. Determine if this alarm is a symptom. If it is, address the root cause first
  2. Open an Opsgenie incident for ACE3C to action for partner reach out
"""

CLOUDWATCH_WORKLOAD_ALARM_PLAYBOOK = """
Partner's CloudWatch telemetry has stopped.

Potential causes:
  1. Could be a symptom of an Indigestion or Replication alarm
  2. Partner's accelerator is failing to aggregate CloudWatch logs

Courses of action:
  1. Determine if this alarm is a symptom. If it is, address the root cause first
  2. Open an Opsgenie incident for ACE3C to action for partner reach out
"""

CORE_WORKLOAD_ALARM_PLAYBOOK = """
Partner's Core Workloads (VPC or Config) telemetry has stopped.

Potential causes:
  1. Could be a symptom of an Indigestion or Replication alarm
  2. Partner's accelerator is failing to aggregate VPC or Config logs

Courses of action:
  1. Determine if this alarm is a symptom. If it is, address the root cause first
  2. Open an Opsgenie incident for ACE3C to action for partner reach out
"""

METADATA_WORKLOAD_ALARM_PLAYBOOK = """
Partner's accelerator metadata telemetry has stopped.

Potential causes:
  1. Could be a symptom of an Indigestion or Replication alarm
  2. Partner's accelerator is failing to publish its metadata

Courses of action:
  1. Determine if this alarm is a symptom. If it is, address the root cause first
  2. Open an Opsgenie incident for ACE3C to action for partner reach out
"""
