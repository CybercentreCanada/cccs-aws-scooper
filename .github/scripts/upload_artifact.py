from boto3 import client
from click import command, option


@command()
@option("--artifact", required=True)
@option("--bucket", required=True)
@option("--key", required=True)
def cli(artifact: str, bucket: str, key: str):
    s3_client = client("s3")
    s3_client.upload_file(Filename=artifact, Bucket=bucket, Key=key)


if __name__ == "__main__":
    cli()
