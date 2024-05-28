from pathlib import Path

from cbs.core.utils.io import read_dict_from_file


def test_read_dict_from_file():
    cdk_options_path = Path("cbs/cdk/cdk.json")

    assert isinstance(read_dict_from_file(cdk_options_path), dict)


def test_read_dict_from_nonexistent_file():
    assert read_dict_from_file(Path()) is None
