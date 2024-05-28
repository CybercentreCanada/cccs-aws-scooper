from datetime import date
from functools import partial
from json import load
from sys import path
from typing import Callable

from aws_cdk import App, Aspects, Environment, Stack
from aws_cdk.assertions import Template
from cdk_nag import AwsSolutionsChecks, NagPackSuppression, NagSuppressions
from pytest import fixture
from yaml import safe_load

path.append("./cbs")

from cbs.cdk.agent.stack import AgentStack
from cbs.cdk.cicd_pipeline.stack import CicdPipelineStack
from cbs.cdk.config import CBSConfig
from cbs.cdk.helpers import create_resource_name
from cbs.core import constants
from docs import VERSION

app = App()
env = Environment(account="111111111111", region="ca-central-1")
partners = {
    "111111111111": {
        constants.ACCOUNT_ID: "111111111111",
        constants.CBS_ID: "testpartner1",
        constants.ACCELERATOR: "asea",
    },
    "222222222222": {
        constants.ACCOUNT_ID: "222222222222",
        constants.CBS_ID: "testpartner2",
        constants.ACCELERATOR: "lza",
    },
}

try:
    with open("cbs/cdk/config/test.yaml", "r") as f:
        config = CBSConfig(**safe_load(f))
except FileNotFoundError:
    with open("config/test.yaml", "r") as f:
        config = CBSConfig(**safe_load(f))

tags = {
    "Owner": "ADS4C",
    "Team": "ADS4C",
    "LastUpdated": str(date.today()),
    "AgentVersion": VERSION,
    "Environment": config.Environment.capitalize(),
}


@fixture(scope="session")
def setup():
    cicd_stack = CicdPipelineStack(
        scope=app,
        construct_id="CicdPipelineStackTesting",
        stack_name="CicdPipelineStackTesting",
        env=env,
        config=config,
        branch=config.Environment,
        deploy_to_env=env,
        tags=tags,
    )
    cbs_stack = AgentStack(
        scope=app,
        construct_id="CbsAwsStackTesting",
        stack_name="CbsAwsStackTesting",
        env=env,
        config=config,
        partners=partners,
        tags=tags,
    )

    return cicd_stack, cbs_stack


@fixture(scope="session")
def _create_resource_name() -> Callable:
    return partial(create_resource_name, environment=config.Environment)


# See https://github.com/cdklabs/cdk-nag/blob/main/RULES.md for all rules
def read_suppressions(exclusions: list[str]) -> list[NagPackSuppression]:
    try:
        with open("cbs/cdk/tests/nag_suppressions.json", "r") as f:
            suppressions = load(f)
    except FileNotFoundError:
        with open("tests/nag_suppressions.json", "r") as f:
            suppressions = load(f)

    return [
        NagPackSuppression(id=id, reason=reason)
        for id, reason in suppressions.items()
        if id not in exclusions
    ]


def suppress_nag(
    stack: Stack,
    exclusions: list[str] = [],
    apply_to_nested_stacks: bool = True,
) -> None:
    NagSuppressions.add_stack_suppressions(
        stack=stack,
        suppressions=read_suppressions(exclusions),
        apply_to_nested_stacks=apply_to_nested_stacks,
    )


@fixture(scope="session")
def cicd_stack_template(setup) -> Template:
    cicd_stack, _ = setup
    return Template.from_stack(cicd_stack)


@fixture(scope="session")
def cbs_stack_template(setup) -> Template:
    _, cbs_stack = setup
    return Template.from_stack(cbs_stack)


@fixture(scope="session")
def cicd_stack_nag(setup) -> Stack:
    cicd_stack, _ = setup
    suppress_nag(cicd_stack)
    Aspects.of(cicd_stack).add(AwsSolutionsChecks())
    return cicd_stack


@fixture(scope="session")
def cbs_stack_nag(setup) -> Stack:
    _, cbs_stack = setup
    suppress_nag(cbs_stack, exclusions=["AwsSolutions-S10"])
    Aspects.of(cbs_stack).add(AwsSolutionsChecks())
    return cbs_stack


@fixture(scope="session")
def mock_partners() -> dict[str, dict[str, str]]:
    return partners
