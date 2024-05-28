from collections.abc import MutableMapping
from dataclasses import asdict, dataclass
from typing import Optional, Union

EXPECTED_CONFIG = {
    "Role": "",
    "Rules": [
        {
            "ID": "cbs",
            "Priority": 0,
            "Filter": {},
            "Status": "Enabled",
            "SourceSelectionCriteria": {
                "SseKmsEncryptedObjects": {"Status": "Enabled"}
            },
            "Destination": {
                "Bucket": "$bucket",
                "Account": "$account",
                "AccessControlTranslation": {"Owner": "Destination"},
                "EncryptionConfiguration": {"ReplicaKmsKeyID": "$replica_kms_key_id"},
                "ReplicationTime": {"Status": "Enabled", "Time": {"Minutes": 15}},
                "Metrics": {"Status": "Enabled", "EventThreshold": {"Minutes": 15}},
            },
            "DeleteMarkerReplication": {"Status": "Disabled"},
        }
    ],
}


@dataclass
class ReplicationDestination:
    Bucket: str
    Account: str
    AccessControlTranslation: dict
    EncryptionConfiguration: dict

    StorageClass: Union[str, None] = None
    ReplicationTime: Optional[dict] = None
    Metrics: Optional[dict] = None


@dataclass
class ReplicationRule:
    ID: str
    Status: str
    SourceSelectionCriteria: dict
    Destination: dict

    Priority: Optional[int] = None
    Prefix: Union[str, None] = None
    Filter: Optional[dict] = None
    ExistingObjectReplication: Union[dict, None] = None
    DeleteMarkerReplication: Optional[dict] = None

    @property
    def replication_destination(self) -> ReplicationDestination:
        return ReplicationDestination(**self.Destination)

    @replication_destination.setter
    def replication_destination(self, __value: ReplicationDestination) -> None:
        self.Destination = asdict(__value)

    def get_value(self, value: str, sep: str = "."):
        parent = self
        for k in value.split(sep):
            try:
                parent = getattr(parent, k)
            except AttributeError:
                try:
                    parent = parent.get(k)
                except AttributeError:
                    return None
        return parent

    def __eq__(self, __value: "ReplicationRule") -> bool:
        # Only check the fields that would actually make a difference to us
        return (
            self.Filter == __value.Filter
            and self.Status == __value.Status
            and self.SourceSelectionCriteria == __value.SourceSelectionCriteria
            and self.replication_destination == __value.replication_destination
            and self.DeleteMarkerReplication == __value.DeleteMarkerReplication
            and self.Prefix == __value.Prefix
        )

    def _flatten_dict_gen(self, d: dict, parent_key: str, sep: str):
        for k, v in d.items():
            new_key = parent_key + sep + k if parent_key else k
            if isinstance(v, MutableMapping):
                yield from self._flatten_dict(v, new_key, sep=sep).items()
            else:
                if new_key not in {"ID", "Priority"}:
                    yield new_key, v

    def _flatten_dict(
        self, d: MutableMapping, parent_key: str = "", sep: str = "."
    ) -> dict:
        return dict(self._flatten_dict_gen(d, parent_key, sep))

    def __sub__(self, __value: "ReplicationRule") -> set[str]:
        return set(self._flatten_dict(asdict(self)).items()) - set(
            self._flatten_dict(asdict(__value)).items()
        )


class ReplicationConfiguration:
    def __init__(self, Role: str, Rules: list[dict]) -> None:
        self.Role = Role
        self.Rules = [ReplicationRule(**rule) for rule in Rules]
