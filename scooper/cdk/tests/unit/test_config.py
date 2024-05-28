"""
The resources contained herein are © His Majesty in Right of Canada as Represented by the Minister of National Defence.

FOR OFFICIAL USE All Rights Reserved. All intellectual property rights subsisting in the resources contained herein are,
and remain the property of the Government of Canada. No part of the resources contained herein may be reproduced or disseminated
(including by transmission, publication, modification, storage, or otherwise), in any form or any means, without the written
permission of the Communications Security Establishment (CSE), except in accordance with the provisions of the Copyright Act, such
as fair dealing for the purpose of research, private study, education, parody or satire. Applications for such permission shall be
made to CSE.

The resources contained herein are provided “as is”, without warranty or representation of any kind by CSE, whether express or
implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement.
In no event shall CSE be liable for any loss, liability, damage or cost that may be suffered or incurred at any time arising
from the provision of the resources contained herein including, but not limited to, loss of data or interruption of business.

CSE is under no obligation to provide support to recipients of the resources contained herein.

This licence is governed by the laws of the province of Ontario and the applicable laws of Canada. Legal proceedings related to
this licence may only be brought in the courts of Ontario or the Federal Court of Canada.

Notwithstanding the foregoing, third party components included herein are subject to the ownership and licensing provisions
noted in the files associated with those components.
"""

from unittest.mock import patch

import botocore
from moto import mock_config  # isolating each test case


def put_attributes(config_client, agg):
    if config_client.describe_configuration_recorders()["ConfigurationRecorders"]:
        print("Existing Configuration Recorder!")
        assert False
    config_client.put_configuration_recorder(
        ConfigurationRecorder={
            "name": "testrecorderconfigtest",
            "roleARN": "arn:aws:iam::account-id:role/role-name",
            "recordingGroup": {
                "allSupported": True,
                "includeGlobalResourceTypes": True,
            },
        }
    )
    if agg == "y":
        config_client.put_configuration_aggregator(
            ConfigurationAggregatorName="test-aggregator",
            AccountAggregationSources=[
                {
                    "AccountIds": [
                        "string",
                    ],
                    "AllAwsRegions": True,
                },
            ],
            Tags=[
                {"Key": "string", "Value": "string"},
            ],
        )
    config_client.put_delivery_channel(
        DeliveryChannel={
            "name": "testchannelmoto",
            "s3BucketName": "string",
            "s3KeyPrefix": "string",
            "s3KmsKeyArn": "string",
            "snsTopicARN": "string",
            "configSnapshotDeliveryProperties": {"deliveryFrequency": "One_Hour"},
        }
    )


orig = botocore.client.BaseClient._make_api_call


def mock_make_api_call(self, operation_name, kwarg):
    if operation_name == "DescribeConfigurationAggregatorSourcesStatus":
        aggstatus = {
            "AggregatedSourceStatusList": [
                {
                    "AwsRegion": "us-east-1",
                    "LastErrorCode": "string",
                    "LastErrorMessage": "string",
                    "LastUpdateStatus": "string",
                    "LastUpdateTime": 0,
                    "SourceId": "string",
                    "SourceType": "string",
                }
            ],
            "NextToken": "string",
        }
        return aggstatus
    elif operation_name == "DescribeDeliveryChannelStatus":
        testdict = {
            "DeliveryChannelsStatus": [
                {
                    "configHistoryDeliveryInfo": {
                        "lastAttemptTime": 0,
                        "lastErrorCode": "string",
                        "lastErrorMessage": "string",
                        "lastStatus": "string",
                        "lastSuccessfulTime": 0,
                        "nextDeliveryTime": 0,
                    },
                    "configSnapshotDeliveryInfo": {
                        "lastAttemptTime": 0,
                        "lastErrorCode": "string",
                        "lastErrorMessage": "string",
                        "lastStatus": "string",
                        "lastSuccessfulTime": 0,
                        "nextDeliveryTime": 0,
                    },
                    "configStreamDeliveryInfo": {
                        "lastErrorCode": "string",
                        "lastErrorMessage": "string",
                        "lastStatus": "string",
                        "lastStatusChangeTime": 0,
                    },
                    "name": "testchannelmoto",
                }
            ]
        }
        return testdict
    return orig(self, operation_name, kwarg)


@patch("botocore.client.BaseClient._make_api_call", new=mock_make_api_call)
@mock_config
def test_enumerate(config_client, sts_client):
    from scooper.sources.native.config import Config

    put_attributes(config_client, "y")
    config_client.start_configuration_recorder(
        ConfigurationRecorderName="testrecorderconfigtest"
    )
    rep = Config("account").report

    print(len(rep.details["configuration"]))
    check = rep.details["configuration"]
    assert (
        check["config_aggregators"]
        and check["config_recorders"]
        and check["delivery_channels"]
    )


@patch("botocore.client.BaseClient._make_api_call", new=mock_make_api_call)
@mock_config
def test_delete_aggregator(config_client, sts_client):
    from scooper.sources.native.config import Config

    put_attributes(config_client, "n")
    agg = config_client.describe_configuration_aggregators()
    if agg["ConfigurationAggregators"]:
        print("Aggregator exists!")
        assert False

    rep = Config("account").report
    assert not rep.details["configuration"]["config_aggregators"]


@patch("botocore.client.BaseClient._make_api_call", new=mock_make_api_call)
@mock_config
def test_delete_recorder(config_client, sts_client):
    from scooper.sources.native.config import Config

    put_attributes(config_client, "y")
    config_client.delete_configuration_recorder(
        ConfigurationRecorderName="testrecorderconfigtest"
    )
    rep = Config("account").report

    assert not rep.details["configuration"]["config_recorders"]
