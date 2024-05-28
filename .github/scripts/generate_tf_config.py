from json import dump
from os import environ

from click import Context, group, option, pass_context


@group()
def cli():
    pass


@cli.command()
@option("--bucket", required=True)
@option("--key", required=True)
@option("--region", default="ca-central-1")
def backend(bucket: str, key: str, region: str):
    s3_backend = {
        # Disables the use of the Amazon EC2 instance metadata service (IMDS).
        # If set to true, user credentials or configuration (like the Region) are not requested from IMDS.
        "skip_metadata_api_check": True,
        "access_key": environ["AWS_ACCESS_KEY_ID"],
        "secret_key": environ["AWS_SECRET_ACCESS_KEY"],
        "token": environ["AWS_SESSION_TOKEN"],
        "bucket": bucket,
        "key": key,
        "region": region,
    }

    with open(f"./.cicd/grafana/{key}.s3.tfbackend.json", "w") as f:
        dump(s3_backend, f)


@cli.command(context_settings=dict(ignore_unknown_options=True, allow_extra_args=True))
@pass_context
def variables(ctx: Context):
    vars = {
        (k[2:] if k.startswith("--") else k): v
        for k, v in [arg.split("=") for arg in ctx.args]
    }
    with open("./.cicd/grafana/grafana.auto.tfvars.json", "w") as f:
        dump(vars, f)


if __name__ == "__main__":
    cli()
