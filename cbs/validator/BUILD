python_sources(
    name="lib",
    interpreter_constraints=[">=3.9"],
    dependencies=[
        ":reqs",
        ":remote_config",
        "cbs/core:cbs_config",
    ]
)

python_requirements(
    name="reqs",
)

resource(
    name="remote_config",
    source="remote_config.json"
)

pex_binary(
    name="cbs_validator",
    dependencies=[":lib"],
    entry_point="__main__.py",
    interpreter_constraints=[">=3.9"],
    output_path="cbs_validator",
)
