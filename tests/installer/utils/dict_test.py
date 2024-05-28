from pytest import raises

from cbs.installer.batch_replication.policies import (
    REPLICATE_EXISTING_OBJECTS_POLICY_PATH,
)
from cbs.installer.utils.dict import dict_template
from cbs.installer.utils.io import load_json_file


def test_dict_template():
    templatable_dict = load_json_file(REPLICATE_EXISTING_OBJECTS_POLICY_PATH)

    assert isinstance(dict_template(templatable_dict, source_bucket_name="test"), dict)


def test_dict_template_without_substitutions():
    templatable_dict = load_json_file(REPLICATE_EXISTING_OBJECTS_POLICY_PATH)

    with raises(KeyError):
        dict_template(templatable_dict)
