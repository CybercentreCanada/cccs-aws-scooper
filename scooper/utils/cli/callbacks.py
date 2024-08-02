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

from __future__ import annotations

from dataclasses import dataclass
from re import compile, match
from typing import Optional, Union

from aws_cdk import aws_s3 as s3
from click import BadParameter, Context, Option


def lifecycle_tokenizer(
    _: Context, __: Option, value: Optional[str]
) -> list[S3LifecycleRule]:
    if value is not None:
        return S3LifecycleTokenizer(value).rules
    return []


@dataclass(frozen=True)
class S3LifecycleRule:
    storage_class: Union[s3.StorageClass, str]
    duration: int


class S3LifecycleTokenizer:
    _pattern = compile(r"([A-Z_]+)\(([\d]+)d\)")

    _storage_classes = {}
    for _attr in dir(s3.StorageClass):
        _attribute = getattr(s3.StorageClass, _attr)
        if isinstance(_attribute, s3.StorageClass):
            _storage_classes[_attr] = _attribute

    def __init__(self, input: str) -> None:
        self.rules: list[S3LifecycleRule] = []
        self._tokenize(input)
        self._validate()

    def _tokenize(self, input: str) -> None:
        for token in input.split(","):
            token = token.strip()
            try:
                if token_match := match(self._pattern, token):
                    storage_class, duration = token_match.groups()
                    self.rules.append(
                        S3LifecycleRule(
                            storage_class=self._storage_classes[storage_class],
                            duration=int(duration),
                        )
                    )
                else:
                    raise BadParameter(f"Invalid lifecycle rules syntax: '{token}'")
            except KeyError:
                if storage_class == "EXPIRY":
                    self.rules.append(S3LifecycleRule(storage_class, int(duration)))
                else:
                    available_storage_classes = list(self._storage_classes.keys()) + [
                        "EXPIRY"
                    ]
                    raise BadParameter(
                        f"'{storage_class}' S3 storage class doesn't exist\nAvailable storage classes: {available_storage_classes}"
                    )

    def _validate(self) -> None:
        expiry_rule = None
        for rule in self.rules:
            if rule.storage_class == "EXPIRY":
                expiry_rule = rule
        if expiry_rule is not None:
            for rule in self.rules:
                if expiry_rule.duration < rule.duration:
                    raise BadParameter(
                        f"'{expiry_rule.storage_class}' duration must be greater than all other rules"
                    )
