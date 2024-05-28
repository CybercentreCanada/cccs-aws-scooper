from datetime import datetime
from json import dump
from re import match

from boto3 import Session
from click import BadParameter, Choice, Context, Option, command, option

from cbs.core import constants


def account_id_checker(ctx: Context, param: Option, value: str) -> str:
    if value is None or match("^[\d]{12}$", value):
        return value
    else:
        raise BadParameter("Account ID must be exactly 12 digits long")


def disclosure_expiry_checker(ctx: Context, param: Option, value: str) -> str:
    try:
        if (
            value == ""
            or value is None
            or datetime.strptime(value, constants.DISCLOSURE_EXPIRY_FORMAT)
        ):
            return value
    except ValueError:
        raise BadParameter(
            "Disclosure expiry must be of the form 'yyyy-mm-ddThh:mm:ss'"
        )


@command()
@option(
    "--action",
    type=Choice(["Read", "Write"]),
    help="Whether to read from or write to the table",
    required=True,
)
@option(
    "--environment",
    help="Environment being deployed",
)
@option(
    "--table_name",
    help="The name of the table to read from or write to",
    required=True,
)
@option(
    "--mgmt_account_id",
    help="Management account ID",
    callback=account_id_checker,
)
@option(
    "--account_id",
    help="Log archive account ID",
    callback=account_id_checker,
)
@option("--cbs_id", help="CBS ID you want to add")
@option("--accelerator", type=Choice(["ASEA", "LZA", "None"]))
@option(
    "--disclosure_expiry",
    help="Datetime to end CBS collection (yyyy-mm-ddThh:mm:ss)",
    callback=disclosure_expiry_checker,
)
def cli(
    action: str,
    environment: str,
    table_name: str,
    mgmt_account_id: str,
    account_id: str,
    cbs_id: str,
    accelerator: str,
    disclosure_expiry: str,
) -> None:
    session = Session()

    ddb_helper = DDBHelper(
        session,
        table_name,
        keys={constants.ACCOUNT_ID, constants.CBS_ID},
    )

    if action == "Read":
        partner_table = ddb_helper.read_table(table_name, ddb_helper.resource)
        with open("partner_table.json", "w") as out:
            dump(partner_table, out, indent=2)
    elif action == "Write":
        if accelerator == "None":
            accelerator = ""
        ddb_helper.add_entry(
            mgmt_account_id=mgmt_account_id,
            account_id=account_id,
            cbs_id=cbs_id,
            accelerator=accelerator.lower(),
            disclosure_expiry=disclosure_expiry,
        )

        if environment == "staging":
            env = "stage"
        elif environment == "production":
            env = "prod"
        else:
            env = None

        # Trigger CI/CD CodePipeline to deploy CDK
        if env is not None:
            codepipeline_client = session.client("codepipeline")
            codepipeline_client.start_pipeline_execution(
                name=f"CBS-CICD-{env}-ca-central-1",
                clientRequestToken=f"Deploying-CBS-For-{cbs_id}",
            )


class DDBHelper:
    def __init__(self, session: Session, table_name: str, keys: set[str]) -> None:
        self.resource = session.resource("dynamodb")
        self.table = self.resource.Table(table_name)
        self.keys = keys

    @staticmethod
    def read_table(table_name: str, ddb_resource) -> list[dict]:
        table = ddb_resource.Table(table_name)
        response = table.scan()
        data: list = response["Items"]

        # If the total number of scanned items exceeds the maximum dataset size limit of 1 MB,
        # extend the dataset by performing enough scans to exhaust the table
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            data.extend(response["Items"])

        return data

    def add_entry(self, **kwargs) -> None:
        data = {k.replace("_", "-"): v for k, v in kwargs.items() if v != ""}

        keys = {k: v for k, v in data.items() if k in self.keys}
        items = {k: v for k, v in data.items() if k not in self.keys}

        for k, v in items.items():
            self.table.update_item(
                Key=keys,
                UpdateExpression="set #fn = :val",
                ExpressionAttributeNames={"#fn": k},
                ExpressionAttributeValues={
                    ":val": v,
                },
            )


if __name__ == "__main__":
    cli()
