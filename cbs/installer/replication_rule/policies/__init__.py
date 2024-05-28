from importlib.resources import files
from pathlib import Path

_traversable = files(__package__)

ASSUME_ROLE_POLICY_PATH = Path(str(_traversable.joinpath("assume_role.json")))
CROSS_ACCOUNT_REPLICATION_POLICY_PATH = Path(
    str(_traversable.joinpath("cross_account_replication.json"))
)

CONTROL_TOWER_CMK_POLICY_PATH = Path(
    str(_traversable.joinpath("control_tower_cmk.json"))
)
REPLICATION_ROLE_CMK_POLICY_PATH = Path(
    str(_traversable.joinpath("replication_role_cmk.json"))
)
