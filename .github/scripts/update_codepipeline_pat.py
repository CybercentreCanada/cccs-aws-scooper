from json import dumps

from boto3 import client
from click import Choice, command, option

secrets_client = client("secretsmanager")
pipeline_client = client("codepipeline")


def rotate_github_pat(token: str) -> None:
    """Updates the GitHub PAT secret

    Args:
        token (str): GitHub PAT
    """
    response = secrets_client.update_secret(
        SecretId="github-token",
        SecretString=dumps({"github-token": token}),
    )
    if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
        print(response)
        print("Something went wrong!")


def get_pipeline(name: str) -> dict:
    """Gets the CodePipeline configuration

    Args:
        name (str): Pipeline name

    Returns:
        dict: Pipeline configuration
    """
    response = pipeline_client.get_pipeline(name=name)
    return response["pipeline"]


def update_pipeline_token(
    pipeline_name: str, pipeline_config: dict, token: str
) -> None:
    """Updates the GitHub OAuth token used for webhooks with newly created PAT

    Args:
        pipeline_name(str): Name of the pipeline
        pipeline_config (dict): Pipeline configuration
        token (str): GitHub PAT
    """
    pipeline_config["stages"][0]["actions"][0]["configuration"]["OAuthToken"] = token
    pipeline_client.update_pipeline(pipeline=pipeline_config)
    pipeline_client.start_pipeline_execution(
        name=pipeline_name,
        clientRequestToken="UpdatingPAT",
    )


@command()
@option(
    "--env",
    help="The CI/CD environment to rotate for",
    type=Choice(["stage", "prod"]),
    required=True,
)
@option(
    "--token",
    help="The new GitHub PAT",
    required=True,
)
def cli(env: str, token: str) -> None:
    pipeline_name = f"CBS-CICD-{env}-ca-central-1"
    rotate_github_pat(token)
    pipeline_config = get_pipeline(pipeline_name)
    update_pipeline_token(pipeline_name, pipeline_config, token)


if __name__ == "__main__":
    cli()
