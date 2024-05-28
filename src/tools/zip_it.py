import os
from argparse import ArgumentParser
from zipfile import ZipFile

from boto3 import client

PATH = "cbs-aws-2/"
KEY = "cbs.zip"
ZIP_PATH = PATH + KEY
BUCKET_NAME = None

IGNORE_DIR_LIST = [
    ".cicd",
    ".git",
    ".github",
    ".idea",
    ".pants.d",
    ".pids",
    ".pytest_cache",
    ".vscode",
    "env",
    ".venv",
    "__pycache__",
    "cdk.out",
    "images",
]
IGNORE_EXT_LIST = [".zip"]

parser = ArgumentParser()
parser.add_argument(
    "-b", "--bucket_name", help="Show Output", default=BUCKET_NAME, required=False
)
args = parser.parse_args()


def is_path_valid(path: str, ignore_dir: list[str], ignore_ext: list[str]) -> bool:
    splited = None
    if os.path.isfile(path):
        if ignore_ext:
            _, ext = os.path.splitext(path)
            if ext in ignore_ext:
                return False

        splited = os.path.dirname(path).split("\\/")
    else:
        if not ignore_dir:
            return True
        splited = path.split("\\/")

    if ignore_dir:
        for s in splited:
            if s in ignore_dir:  # You can also use set.intersection or [x for],
                return False

    return True


def zip_dir_helper(
    path: str,
    root_dir: str,
    zf: ZipFile,
    ignore_dir: list[str] = None,
    ignore_ext: list[str] = None,
) -> None:
    # zf is zipfile handle
    if os.path.isfile(path):
        if is_path_valid(path, ignore_dir, ignore_ext):
            relative = os.path.relpath(path, root_dir)
            zf.write(path, relative)
        return

    ls = os.listdir(path)
    for sub_file_or_dir in ls:
        if not is_path_valid(sub_file_or_dir, ignore_dir, ignore_ext):
            continue

        joined_path = os.path.join(path, sub_file_or_dir)
        zip_dir_helper(joined_path, root_dir, zf, ignore_dir, ignore_ext)


def zip_dir(
    path: str,
    zf: ZipFile,
    ignore_dir: list[str] = None,
    ignore_ext: list[str] = None,
    close: bool = False,
) -> None:
    root_dir = path if os.path.isdir(path) else os.path.dirname(path)

    try:
        zip_dir_helper(path, root_dir, zf, ignore_dir, ignore_ext)
    finally:
        if close:
            zf.close()


def main() -> None:
    root_path = os.path.abspath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../..")
    )
    os.chdir(root_path)
    zip_obj = ZipFile(ZIP_PATH, "w")
    zip_dir(
        PATH,
        zip_obj,
        ignore_dir=IGNORE_DIR_LIST,
        ignore_ext=IGNORE_EXT_LIST,
        close=True,
    )

    s3_client = client("s3")
    s3_client.upload_file(ZIP_PATH, Bucket=args.bucket_name, Key=KEY)

    os.remove(ZIP_PATH)

    print(f"File {KEY} uploaded to {args.bucket_name}")


if __name__ == "__main__":
    main()
