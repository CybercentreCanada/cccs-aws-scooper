from sys import path
from typing import TYPE_CHECKING

from moto import mock_aws
from pytest import raises

from cbs.core import constants as core_constants
from cbs.lambdas import PATH as LAMBDAS_PATH

from . import constants

path.append(f"{LAMBDAS_PATH}/transport")

if TYPE_CHECKING:
    from cbs.lambdas.transport.exceptions import TransportError
else:
    from exceptions import TransportError

from .helpers import make_s3_replication_notifications
from .object_key_to_expected_workload_mappings import (
    ASEA_OBJECT_KEY_TO_WORKLOAD_MAP,
    LZA_OBJECT_KEY_TO_WORKLOAD_MAP,
)

TEST_MAP_TO_ACTUAL_MAP = {
    "asea": (
        ASEA_OBJECT_KEY_TO_WORKLOAD_MAP,
        core_constants.ASEA_LOG_TYPE_REGEX_TO_WORKLOAD_MAP,
    ),
    "lza": (
        LZA_OBJECT_KEY_TO_WORKLOAD_MAP,
        core_constants.LZA_LOG_TYPE_REGEX_TO_WORKLOAD_MAP,
    ),
}


@mock_aws
def test_workload_regular_expressions(mock_context):
    from cbs.lambdas.transport.transport import Transport

    for accelerator, mappings in TEST_MAP_TO_ACTUAL_MAP.items():
        test_map, actual_map = mappings

        transport = Transport()
        transport.partners = {
            constants.PARTNER_ACCOUNT_ID: {
                core_constants.CBS_ID: constants.CBS_ID,
                core_constants.ACCELERATOR: accelerator,
                core_constants.DEPLOYED: True,
                core_constants.VPC_CUSTOM_FIELDS: ",".join(
                    core_constants.DEFAULT_VPC_FLOW_LOG_FIELDS
                ),
            }
        }

        # Checks inference for workloads based on a match within the log type regex map
        for object_key, workload in test_map.items():
            # Don't test metadata.json object key since it tries to check
            # the object itself to reconcile against which accelerator it already knows of
            if object_key != "metadata.json":
                if workload is None:
                    with raises(TransportError):
                        transport.process_s3_event(
                            make_s3_replication_notifications(
                                object_key, "test-bucket"
                            ),
                            mock_context,
                        )
                else:
                    transport.process_s3_event(
                        make_s3_replication_notifications(object_key, "test-bucket"),
                        mock_context,
                    )
                assert transport.cbs_event.workload == workload

        # Make sure we're testing every available mapping
        test_workloads = set(filter(lambda value: value is not None, test_map.values()))
        workloads = set(actual_map.values())

        assert (
            test_workloads == workloads
        ), f"Missing test(s) for {workloads - test_workloads} in {accelerator.upper()}"
