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

import sys
from io import BytesIO
from pathlib import Path
from types import ModuleType
from urllib.request import urlopen
from zipfile import ZipFile

import boto3


class LambdaLayer:
    path = Path("/tmp/lambda_layers")
    full_path = path / Path("python")

    def _exists(self, layer_name: str) -> bool:
        """Check if Lambda Layer has already been downloaded."""
        return Path(LambdaLayer.full_path / layer_name).exists()

    def _download(self, arn: str, module_name: str) -> None:
        """Download and extract Lambda Layer."""
        # Get information about Lambda Layer
        client = boto3.client("lambda")
        response = client.get_layer_version_by_arn(Arn=arn)
        url = response["Content"]["Location"]
        # Download Lambda Layer and extract zip to /tmp
        with urlopen(url) as zipresp:
            with ZipFile(BytesIO(zipresp.read())) as zfile:
                self._validate(zfile, module_name)
                zfile.extractall(LambdaLayer.path)

    def _validate(self, zip_file: ZipFile, module_name: str):
        unexpected_module_items = [
            path
            for path in zip_file.namelist()
            if not path.startswith("python/%s" % module_name)
        ]

        if unexpected_module_items:
            raise ValueError(
                "Unexpected module paths found when unzipping module %s" % module_name
            )

    def import_layer(self, layer_version_arn: str, module_name: str) -> ModuleType:
        """Add Lambda Layer to PYTHONPATH."""
        if not self._exists(module_name):
            self._download(layer_version_arn, module_name)

        sys.path.append(str(LambdaLayer.full_path))
