"""
The resources contained herein are © His Majesty in Right of Canada as Represented by the Minister of National Defence.

FOR OFFICIAL USE All Rights Reserved. All intellectual property rights subsisting in the resources contained herein are,
and remain the property of the Government of Canada. No part of the resources contained herein may be reproduced or disseminated
(including by transmission, publication, modification, storage, or otherwise), in any form or any means, without the written
permission of the Communications Security Establishment (CSE), except in accordance with the provisions of the Copyright Act, such
as fair dealing for the purpose of research, private study, education, parody or satire. Applications for such permission shall be
made to CSE.

The resources contained herein are provided “as is”, without warranty or representation of any kind by CSE, whether express or
implied, including but not limited to the warranties of merchantability, fitness for a particular purpose and noninfringement.
In no event shall CSE be liable for any loss, liability, damage or cost that may be suffered or incurred at any time arising
from the provision of the resources contained herein including, but not limited to, loss of data or interruption of business.

CSE is under no obligation to provide support to recipients of the resources contained herein.

This licence is governed by the laws of the province of Ontario and the applicable laws of Canada. Legal proceedings related to
this licence may only be brought in the courts of Ontario or the Federal Court of Canada.

Notwithstanding the foregoing, third party components included herein are subject to the ownership and licensing provisions
noted in the files associated with those components.
"""

from collections.abc import Collection
from io import BytesIO
from pathlib import Path
from sys import modules
from sys import path as syspath
from tempfile import mkdtemp
from types import ModuleType
from urllib.request import urlopen
from zipfile import ZipFile

from boto3 import client

from scooper.core.utils.logger import get_logger

METADATA_SOURCES_LAMBDA_LAYER_ARN = (
    "arn:aws:lambda:ca-central-1:495075646178:layer:CBSMetadataSourcesLambdaLayer"
)
METADATA_SOURCES_LAMBDA_LAYER_VERSION = 34
METADATA_SOURCES_LAMBDA_LAYER_VERSION_ARN = (
    f"{METADATA_SOURCES_LAMBDA_LAYER_ARN}:{METADATA_SOURCES_LAMBDA_LAYER_VERSION}"
)
# Metadata source packages in the layer that Scooper collects from
METADATA_SOURCES = ("iam", "organization", "sso")

_logger = get_logger()


class LambdaLayer:
    # Per-user cache: code extracted to a shared location like /tmp could be planted by other users
    path = Path.home() / ".cache" / "scooper" / "lambda_layers"

    @classmethod
    def _extract_path(cls, layer_version_arn: str) -> Path:
        """Get the directory a Lambda Layer version is extracted to: `<path>/<layer name>/<version>`."""
        layer_name, version = layer_version_arn.split(":")[-2:]
        return cls.path / layer_name / version

    @classmethod
    def _download(cls, arn: str, packages: Collection[str], extract_path: Path) -> None:
        """Download Lambda Layer and extract only the given top-level packages."""
        _logger.info("Downloading Lambda Layer '%s'...", arn)
        lambda_client = client("lambda")
        response = lambda_client.get_layer_version_by_arn(Arn=arn)
        url = response["Content"]["Location"]

        with urlopen(url) as zipresp, ZipFile(BytesIO(zipresp.read())) as zfile:
            prefixes = tuple(f"python/{package}/" for package in packages)
            members = [name for name in zfile.namelist() if name.startswith(prefixes)]

            if missing := set(packages) - {name.split("/")[1] for name in members}:
                raise ValueError(
                    f"Lambda Layer '{arn}' is missing packages: {sorted(missing)}"
                )

            extract_path.parent.mkdir(parents=True, exist_ok=True)
            # Extract to a staging directory first so an interrupted extraction is never mistaken for a complete one
            staging_path = Path(mkdtemp(dir=extract_path.parent))
            zfile.extractall(staging_path, members)
            staging_path.rename(extract_path)

    @classmethod
    def import_layer(
        cls,
        layer_version_arn: str,
        packages: Collection[str],
        root_package: str | None = None,
    ) -> None:
        """Make the given top-level packages of a Lambda Layer importable, also as subpackages of `root_package` if given."""
        extract_path = cls._extract_path(layer_version_arn)

        if not extract_path.exists():
            cls._download(layer_version_arn, packages, extract_path)

        layer_root = str(extract_path / "python")
        # Prepend so the pinned layer takes precedence over any installed modules with the same names
        syspath.insert(0, layer_root)

        if root_package:
            # For layers built by flattening a package into their root, whose code still imports it by name
            package = ModuleType(root_package)
            package.__path__ = [layer_root]
            modules[root_package] = package
