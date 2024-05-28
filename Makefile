clean:
	find . -name '__pycache__' -exec rm -rf {} +
	find . -name '.pants.d' -exec rm -rf {} +
	find . -name '.pids' -exec rm -rf {} +
	find . -name '.pytest_cache' -exec rm -rf {} +
	find . -name 'dist' -exec rm -rf {} +
	find . -name 'cdk.out' -exec rm -rf {} +
	find . -name '.aws-sam' -exec rm -rf {} +
	find . -name '.ruff_cache' -exec rm -rf {} +
