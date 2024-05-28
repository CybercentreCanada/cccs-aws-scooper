"""
Effectively a translation of this script:
https://github.com/aws-samples/blog-devops-iamra/blob/main/generate-certs.sh
"""

from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

# Generate our key
ca_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# Write our key to disk for safe keeping
with open("ca.key", "wb") as f:
    f.write(
        ca_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


# Various details about who we are. For a self-signed certificate the
# subject and issuer are always the same.
subject = issuer = x509.Name(
    [
        x509.NameAttribute(NameOID.COUNTRY_NAME, "CA"),
        x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Ontario"),
        x509.NameAttribute(NameOID.LOCALITY_NAME, "Ottawa"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "CCCS"),
        x509.NameAttribute(NameOID.COMMON_NAME, "CBS"),
    ]
)

cert = (
    x509.CertificateBuilder()
    .subject_name(subject)
    .issuer_name(issuer)
    .public_key(ca_key.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.now(timezone.utc))
    .not_valid_after(
        # Our certificate will be valid for 1 year
        datetime.now(timezone.utc)
        + timedelta(days=365)
    )
    .add_extension(
        x509.KeyUsage(
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
        x509.BasicConstraints(True, None),
        critical=True,
        # Sign our certificate with our private key
    )
    .sign(ca_key, hashes.SHA256())
)

# Write our certificate out to disk
with open("ca.crt", "wb") as f:
    f.write(cert.public_bytes(serialization.Encoding.PEM))


# Generate our key for leaf certificate
private_key = rsa.generate_private_key(
    public_exponent=65537,
    key_size=2048,
)

# Write our key to disk for safe keeping
with open("private.key", "wb") as f:
    f.write(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


# Generate a CSR
csr = (
    x509.CertificateSigningRequestBuilder()
    .subject_name(
        x509.Name(
            [
                # Provide various details about who we are.
                x509.NameAttribute(NameOID.COUNTRY_NAME, "CA"),
                x509.NameAttribute(NameOID.STATE_OR_PROVINCE_NAME, "Ontario"),
                x509.NameAttribute(NameOID.LOCALITY_NAME, "Ottawa"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "CCCS"),
                x509.NameAttribute(NameOID.COMMON_NAME, "CBS"),
            ]
        )
    )
    .add_extension(
        x509.KeyUsage(
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
    .sign(private_key, hashes.SHA256())
)

# Write our CSR out to disk
with open("iamra-cert.csr", "wb") as f:
    f.write(csr.public_bytes(serialization.Encoding.PEM))


# Sign leaf certificate with CA
leaf_cert = (
    x509.CertificateBuilder()
    .subject_name(csr.subject)
    .issuer_name(cert.issuer)
    .public_key(csr.public_key())
    .serial_number(x509.random_serial_number())
    .not_valid_before(datetime.now(timezone.utc))
    .not_valid_after(
        # Our certificate will be valid for 1 year
        datetime.now(timezone.utc)
        + timedelta(days=365)
    )
    .add_extension(
        x509.KeyUsage(
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
    .sign(ca_key, hashes.SHA256())
)

# Write our leaf certificate out to disk
with open("certificate.crt", "wb") as f:
    f.write(leaf_cert.public_bytes(serialization.Encoding.PEM))
