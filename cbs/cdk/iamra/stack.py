from functools import partial

import aws_cdk as cdk
from aws_cdk import aws_iam as iam
from constructs import Construct

from cbs.cdk.config import CBSConfig
from cbs.cdk.helpers import create_resource_name


class IAMRolesAnywhereStack(cdk.NestedStack):
    def __init__(
        self, scope: Construct, id: str, config: CBSConfig, role: iam.Role, **kwargs
    ) -> None:
        super().__init__(scope, id, **kwargs)

        _create_resource_name = partial(
            create_resource_name, scope=self, environment=config.Environment
        )

        cdk.CfnResource(
            self,
            "TrustAnchor",
            type="AWS::RolesAnywhere::TrustAnchor",
            properties={
                "Name": _create_resource_name("TrustAnchor"),
                "Source": {
                    "SourceData": {
                        "X509CertificateData": cdk.SecretValue.secrets_manager(
                            _create_resource_name("CACertificate")
                        ).unsafe_unwrap()
                    },
                    "SourceType": "CERTIFICATE_BUNDLE",
                },
                "Enabled": True,
            },
        )

        cdk.CfnResource(
            self,
            "Profile",
            type="AWS::RolesAnywhere::Profile",
            properties={
                "Name": _create_resource_name("Profile"),
                "RoleArns": [role.role_arn],
                "DurationSeconds": 3600,
                "Enabled": True,
            },
        )
