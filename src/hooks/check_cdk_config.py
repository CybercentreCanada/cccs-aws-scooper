from re import match
from sys import argv

from yaml import safe_load


def check_cdk_config(config_files: list[str], sensitive_values: list[str]) -> int:
    retv = 0

    for config_file in config_files:
        with open(config_file, "r") as f:
            config = safe_load(f)
            for sensitive_value in sensitive_values:
                if config.get(sensitive_value):
                    print(
                        f"Sensitive value '{sensitive_value}' found in '{config_file}'"
                    )
                    retv = 1

    return retv


def main() -> int:
    config_files = []
    sensitive_values = []

    for arg in argv[1:]:
        if match("(^.*config/.*\.yaml$)", arg):
            config_files.append(arg)
        else:
            sensitive_values.append(arg)

    return check_cdk_config(config_files, sensitive_values)


if __name__ == "__main__":
    raise SystemExit(main())
