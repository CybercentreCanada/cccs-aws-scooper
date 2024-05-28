from typing import TypedDict


class Partner(TypedDict):
    # Guaranteed fields
    account_id: str
    cbs_id: str
    accelerator: str
    bucket_name: str
    kms_arn: str
    deployed: bool

    # Conditional fields
    org_id: str | None
    mgmt_account_id: str | None
    vpc_custom_fields: str | None
    disclosure_expiry: str | None
