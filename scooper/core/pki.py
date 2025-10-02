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

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    load_pem_private_key,
)
from cryptography.x509 import (
    BasicConstraints,
    CertificateBuilder,
    CertificateSigningRequestBuilder,
    KeyUsage,
    Name,
    NameAttribute,
    load_pem_x509_certificate,
    random_serial_number,
)
from cryptography.x509.oid import NameOID

from scooper.core.constants import SCOOPER
from scooper.core.lambda_layer import CBS_COMMON_LAMBDA_LAYER_VERSION_ARN, LambdaLayer

LambdaLayer.import_layer(CBS_COMMON_LAMBDA_LAYER_VERSION_ARN, "cbs_common")

from cbs_common.datetimes import utc_now


class _Certificate:
    def __init__(self) -> None:
        self.private_key_path = Path(
            f"pki/{self.__class__.__name__.lower()}/private.key"
        )

        if self.private_key_path.exists():
            with self.private_key_path.open() as f:
                self.private_key = load_pem_private_key(
                    f.read().encode(), password=None
                )
        else:
            self.private_key = generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )

            if not self.private_key_path.parent.exists():
                self.private_key_path.parent.mkdir(parents=True, exist_ok=True)

            self.private_key_path.write_bytes(
                self.private_key.private_bytes(
                    encoding=Encoding.PEM,
                    format=PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=NoEncryption(),
                )
            )

        self.certificate_path = Path(
            f"pki/{self.__class__.__name__.lower()}/certificate.crt"
        )
        self.certificate = None


class CertificateAuthority(_Certificate):
    """Self-signed certificate authority."""

    def __init__(self, validity: timedelta) -> None:
        super().__init__()

        if self.certificate_path.exists():
            with self.certificate_path.open() as f:
                self.certificate = load_pem_x509_certificate(f.read().encode())

        if self.certificate is None or self.certificate.not_valid_after_utc < utc_now():
            subject = issuer = Name([NameAttribute(NameOID.COMMON_NAME, SCOOPER)])
            self.certificate = (
                CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(self.private_key.public_key())
                .serial_number(random_serial_number())
                .not_valid_before(datetime.now(timezone.utc))
                .not_valid_after(datetime.now(timezone.utc) + validity)
                .add_extension(
                    KeyUsage(
                        digital_signature=True,
                        content_commitment=False,
                        key_encipherment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        key_cert_sign=True,
                        crl_sign=True,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
                .add_extension(
                    BasicConstraints(True, None),
                    critical=True,
                    # Sign our certificate with our private key
                )
                .sign(self.private_key, SHA256())
            )

            if not self.certificate_path.parent.exists():
                self.certificate_path.parent.mkdir(parents=True, exist_ok=True)

            self.certificate_path.write_bytes(
                self.certificate.public_bytes(Encoding.PEM)
            )


class LeafCertificate(_Certificate):
    """Certificate authority-signed leaf certificate."""

    def __init__(self, certificate_authority: CertificateAuthority) -> None:
        super().__init__()

        if self.certificate_path.exists():
            with self.certificate_path.open() as f:
                self.certificate = load_pem_x509_certificate(f.read().encode())

        if self.certificate is None or self.certificate.not_valid_after_utc < utc_now():
            certificate_signing_request = (
                CertificateSigningRequestBuilder()
                .subject_name(
                    Name(
                        [
                            NameAttribute(NameOID.COMMON_NAME, SCOOPER),
                        ]
                    )
                )
                .add_extension(
                    KeyUsage(
                        digital_signature=True,
                        content_commitment=False,
                        key_encipherment=True,
                        data_encipherment=True,
                        key_agreement=False,
                        key_cert_sign=False,
                        crl_sign=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                    # Sign the CSR with our private key
                )
                .sign(self.private_key, SHA256())
            )
            self.certificate = (
                CertificateBuilder()
                .subject_name(certificate_signing_request.subject)
                .issuer_name(certificate_authority.certificate.issuer)
                .public_key(certificate_signing_request.public_key())
                .serial_number(random_serial_number())
                .not_valid_before(datetime.now(timezone.utc))
                .not_valid_after(certificate_authority.certificate.not_valid_after_utc)
                .add_extension(
                    KeyUsage(
                        digital_signature=True,
                        content_commitment=False,
                        key_encipherment=True,
                        data_encipherment=True,
                        key_agreement=False,
                        key_cert_sign=False,
                        crl_sign=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                    # Sign our leaf certificate with our CA key
                )
                .sign(certificate_authority.private_key, SHA256())
            )

            if not self.certificate_path.parent.exists():
                self.certificate_path.parent.mkdir(parents=True, exist_ok=True)

            self.certificate_path.write_bytes(
                self.certificate.public_bytes(Encoding.PEM)
            )
