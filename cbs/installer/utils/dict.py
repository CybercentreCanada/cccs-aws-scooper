from json import dumps, loads
from string import Template


def dict_template(templatable_dict: dict, **kwargs) -> dict:
    """Template a dict with given kwargs."""
    return loads(Template(dumps(templatable_dict)).substitute(**kwargs))
