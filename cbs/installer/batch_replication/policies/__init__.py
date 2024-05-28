from importlib.resources import files
from pathlib import Path

_traversable = files(__package__)

ASSUME_ROLE_POLICY_PATH = Path(str(_traversable.joinpath("assume_role.json")))
REPLICATE_EXISTING_OBJECTS_POLICY_PATH = Path(
    str(_traversable.joinpath("replicate_existing_objects.json"))
)
