from json import load
from pathlib import Path


def read_dict_from_file(dict_path: Path) -> dict:
    """Check if given dict_path is a valid file and then serialize its contents as a dict."""
    if dict_path.is_file():
        with dict_path.open("r") as f:
            return load(f)
