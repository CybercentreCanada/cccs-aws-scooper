from boto3 import Session
from core import constants
from core.types import Partner


def read_partner_inventory_table(
    table_name: str, session: Session
) -> dict[str, Partner]:
    table = session.resource("dynamodb").Table(table_name)
    response = table.scan()
    data: list[Partner] = response["Items"]

    while "LastEvaluatedKey" in response:
        response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
        data.extend(response["Items"])

    return {partner[constants.ACCOUNT_ID]: partner for partner in data}
