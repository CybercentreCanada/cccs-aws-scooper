import playbooks

INDIGESTION_ALARM = "IndigestionAlarm"
REPLICATION_ALARM = "ReplicationAlarm"
CLOUDTRAIL_WORKLOAD_ALARM = "CloudTrailWorkloadAlarm"
CLOUDWATCH_WORKLOAD_ALARM = "CloudWatchWorkloadAlarm"
CORE_WORKLOAD_ALARM = "CoreWorkloadAlarm"
METADATA_WORKLOAD_ALARM = "MetadataWorkloadAlarm"

P1_ALARMS = frozenset(
    {
        INDIGESTION_ALARM: (
            "Downstream Processing Failing!",
            playbooks.INDIGESTION_ALARM_PLAYBOOK,
        ),
        REPLICATION_ALARM: (
            "Replication Failing!",
            playbooks.REPLICATION_ALARM_PLAYBOOK,
        ),
    }.items()
)
P2_ALARMS = frozenset(
    {
        CLOUDTRAIL_WORKLOAD_ALARM: (
            "CloudTrail Logs Missing!",
            playbooks.CLOUDTRAIL_WORKLOAD_ALARM_PLAYBOOK,
        ),
    }.items()
)
P3_ALARMS = frozenset(
    {
        CLOUDWATCH_WORKLOAD_ALARM: (
            "CloudWatch Logs Missing!",
            playbooks.CLOUDWATCH_WORKLOAD_ALARM_PLAYBOOK,
        ),
        CORE_WORKLOAD_ALARM: (
            "VPC or Config Logs Missing!",
            playbooks.CORE_WORKLOAD_ALARM_PLAYBOOK,
        ),
    }.items()
)
P4_ALARMS = frozenset(
    {
        METADATA_WORKLOAD_ALARM: (
            "Accelerator Metadata Missing!",
            playbooks.METADATA_WORKLOAD_ALARM_PLAYBOOK,
        ),
    }.items()
)

ALARM_PRIORITIES = {
    P1_ALARMS: "P1",
    P2_ALARMS: "P2",
    P3_ALARMS: "P3",
    P4_ALARMS: "P4",
}
