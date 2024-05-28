python_sources(
    name="lib",
    sources=[
        "*.py",
        "*/*.py",
        "!tests/",
    ],
    interpreter_constraints=[">=3.9"],
    dependencies=[
        ":reqs",
        ":remote_config",
        "cbs/core:cbs_config",
        "cbs/core/utils:lib",
        ":policies",
        ":terraform",
    ]
)

python_requirements(
    name="reqs",
)

resource(
    name="remote_config",
    source="remote_config.json",
)

resources(
    name="policies",
    sources=["*/policies/*"],
)

resources(
    name="terraform",
    sources=["terraform/*"],
)

pex_binary(
    name="cbs",
    dependencies=[":lib"],
    entry_point="__main__.py",
    interpreter_constraints=[">=3.9"],
    output_path="cbs",
)
