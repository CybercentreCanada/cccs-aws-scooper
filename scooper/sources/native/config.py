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

from boto3 import client

from scooper.sources import LogSource
from scooper.sources.report import LoggingReport
from scooper.utils.enum import paginate
from scooper.utils.logger import get_logger

_logger = get_logger()


class Config(LogSource):
    def __init__(self, level: str) -> None:
        super().__init__()
        self._level = level
        self._service = self.__class__.__name__
        self._client = client(self._service.lower())

    def _enumerate_config_aggregators(self) -> dict[str, dict]:
        _logger.info("Enumerating Configuration Aggregators...")
        config_aggregators = paginate(
            self._client,
            "describe_configuration_aggregators",
            "ConfigurationAggregators",
        )

        # Update aggregators with status information
        config_aggregators = {
            aggregator["ConfigurationAggregatorName"]: aggregator
            for aggregator in config_aggregators
        }
        for aggregator in config_aggregators:
            config_aggregators.update(
                {
                    aggregator: paginate(
                        self._client,
                        "describe_configuration_aggregator_sources_status",
                        "AggregatedSourceStatusList",
                        ConfigurationAggregatorName=aggregator,
                    )[0]
                }
            )

        return config_aggregators

    def _enumerate_config_recorders(self) -> dict[str, dict]:
        _logger.info("Enumerating Configuration Recorders...")

        config_recorders = self._client.describe_configuration_recorders()[
            "ConfigurationRecorders"
        ]
        config_recorder_status = self._client.describe_configuration_recorder_status()[
            "ConfigurationRecordersStatus"
        ]

        # Join dicts on common 'name' key
        config_recorders = {recorder["name"]: recorder for recorder in config_recorders}
        for status in config_recorder_status:
            config_recorders[status["name"]].update(status)

        return config_recorders

    def _enumerate_delivery_channels(self) -> dict[str, dict]:
        _logger.info("Enumerating Delivery Channels...")

        delivery_channels = self._client.describe_delivery_channels()[
            "DeliveryChannels"
        ]
        delivery_channel_status = self._client.describe_delivery_channel_status()[
            "DeliveryChannelsStatus"
        ]

        # Join dicts on common 'name' key
        delivery_channels = {channel["name"]: channel for channel in delivery_channels}
        for status in delivery_channel_status:
            delivery_channels[status["name"]].update(status)

        return delivery_channels

    def enumerate(self) -> tuple[dict[str, dict]]:
        _logger.info("Enumerating %s...", self._service)

        config_aggregators = self._enumerate_config_aggregators()
        config_recorders = self._enumerate_config_recorders()
        delivery_channels = self._enumerate_delivery_channels()

        return config_aggregators, config_recorders, delivery_channels

    def get_report(self) -> LoggingReport:
        config_aggregators, config_recorders, delivery_channels = self.enumerate()

        config_enabled = False
        scooper_owned = []

        for aggregator_name, aggregator in config_aggregators.items():
            if aggregator.get("LastUpdateStatus") == "SUCCEEDED":
                _logger.info(
                    "Config aggregator '%s' is already configured!", aggregator_name
                )
                config_enabled = True
                scooper_owned.append("Scooper" in aggregator_name)

        for recorder_name, recorder in config_recorders.items():
            if recorder.get("recording"):
                _logger.info(
                    "Config recorder '%s' is already configured!", recorder_name
                )
                config_enabled = True
                scooper_owned.append("Scooper" in recorder_name)

        return LoggingReport(
            service=self._service,
            enabled=config_enabled,
            details={
                "level": self.level,
                "configuration": {
                    "config_aggregators": config_aggregators,
                    "config_recorders": config_recorders,
                    "delivery_channels": delivery_channels,
                },
            },
            owned_by_scooper=any(scooper_owned),
        )
