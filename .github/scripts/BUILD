python_source(
    name="upload_artifact",
    source="upload_artifact.py",
    dependencies=[":reqs"],
)

python_source(
    name="generate_tf_config",
    source="generate_tf_config.py",
    dependencies=[":reqs"],
)

python_source(
    name="modify_dynamodb",
    source="modify_dynamodb.py",
    dependencies=[
        ":reqs",
        "cbs/core:constants",
    ],
)

python_requirements(name="reqs")
