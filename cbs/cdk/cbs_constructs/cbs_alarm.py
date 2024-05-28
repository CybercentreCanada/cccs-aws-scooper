import aws_cdk.aws_cloudwatch as cloudwatch
import aws_cdk.aws_cloudwatch_actions as cloudwatch_actions
import aws_cdk.aws_sns as sns
from constructs import Construct


class CBSAlarm(cloudwatch.Alarm):
    def __init__(self, scope: Construct, id: str, topic: sns.ITopic, **kwargs):
        super().__init__(scope, id, **kwargs)
        super().add_alarm_action(cloudwatch_actions.SnsAction(topic))
        super().add_ok_action(cloudwatch_actions.SnsAction(topic))
