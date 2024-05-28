#!/usr/bin/env python3
from datetime import date
from os import getenv
from pathlib import Path
from sys import path

import aws_cdk as cdk
from config import CBSConfig, ConfigManager
from yaml import safe_load

cbs_dir = Path(__file__).cwd().parent
root_dir = cbs_dir.parent
path.append(str(cbs_dir))
path.append(str(root_dir))

from cbs.cdk.agent.stack import AgentStack
from cbs.cdk.cicd_pipeline.stack import CicdPipelineStack
from cbs.cdk.helpers import create_resource_name
from cbs.core.utils.io import read_dict_from_file
from docs import VERSION

app = cdk.App()

account = getenv("CDK_DEFAULT_ACCOUNT")
region = getenv("CDK_DEFAULT_REGION", "ca-central-1")

if environment := app.node.try_get_context("config"):
    match environment:
        case "dev" | "test":
            with open(f"./config/{environment}.yaml", "r") as f:
                config = CBSConfig(**safe_load(f))
        case "stage" | "prod":
            config = ConfigManager(environment).remote_config
        case _:
            raise SystemExit(f"Error: Unrecognized environment '{environment}'")

    tags = {
        "Owner": "ADS4C",
        "Team": "ADS4C",
        "LastUpdated": str(date.today()),
        "AgentVersion": VERSION,
        "Environment": config.Environment.capitalize(),
    }

    if config.OnlyAgent:
        stack_name = create_resource_name(
            resource_name="Agent", environment=config.Environment
        )
        AgentStack(
            scope=app,
            construct_id=stack_name,
            stack_name=stack_name,
            env=cdk.Environment(account=account, region=region),
            config=config,
            partners=read_dict_from_file(Path("partner_inventory.json"))
            or read_dict_from_file(Path("cbs/cdk/partner_inventory.json")),
            tags=tags,
        )
    else:
        stack_name = create_resource_name(
            resource_name="CICD", environment=config.Environment
        )
        match config.Environment:
            case "prod":
                branch = "production"
            case "stage":
                branch = "staging"
            case _:
                branch = None
        CicdPipelineStack(
            scope=app,
            construct_id=stack_name,
            stack_name=stack_name,
            env=cdk.Environment(account=account, region=region),
            config=config,
            branch=branch,
            deploy_to_env=cdk.Environment(account=config.AgentAccount, region=region),
            tags=tags,
            termination_protection=config.Environment == "prod",
        )
else:
    raise SystemExit(
        "Error: You must pass the 'config' context parameter. Please refer to the README"
    )

app.synth()
