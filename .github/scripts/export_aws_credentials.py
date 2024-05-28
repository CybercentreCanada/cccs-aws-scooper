from json import load
from os import environ


def load_creds() -> dict[str, str | int]:
    with open("temporary_credentials.json", "r") as f:
        return load(f)


def export_creds(creds: dict) -> None:
    with open(environ["GITHUB_OUTPUT"], "a") as gh_out:
        for k, v in creds.items():
            print(f"{k}={str(v)}", file=gh_out)


if __name__ == "__main__":
    creds = load_creds()
    export_creds(creds)
