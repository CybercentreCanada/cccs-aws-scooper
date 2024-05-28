from pathlib import Path
from re import search
from sys import argv

from docs import VERSION


def check_version(changelog_path: Path) -> int:
    retv = 0

    with changelog_path.open() as f:
        changelog = f.read()

    if match := search("\[(\d+.){3}\]", changelog):
        if VERSION < match.group(1):
            retv = 1
            print(
                (
                    f"Version '{VERSION}' is less than the version found in the changelog.\n"
                    "Make sure to update the version to the newest changelog's version!"
                )
            )

    if not search(f"\[{VERSION}\]", changelog):
        retv = 1
        print(
            (
                f"Version '{VERSION}' was not found in the changelog.\n"
                "Make sure to update the changelog with the newest version's changes!"
            )
        )

    return retv


def main() -> int:
    changelog_path = Path(argv[1])

    return check_version(changelog_path)


if __name__ == "__main__":
    raise SystemExit(main())
