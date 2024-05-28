from aws_cdk import Stack
from aws_cdk.assertions import Annotations, Match


def test_cicd_stack_nag(cicd_stack_nag: Stack):
    errors = Annotations.from_stack(cicd_stack_nag).find_error(
        "*", Match.string_like_regexp("AwsSolutions-.*")
    )
    assert len(errors) == 0, f"CDK NAG returned {len(errors)} error(s)"


def test_cbs_stack_nag(cbs_stack_nag: Stack):
    errors = Annotations.from_stack(cbs_stack_nag).find_error(
        "*", Match.string_like_regexp("AwsSolutions-.*")
    )
    assert len(errors) == 0, f"CDK NAG returned {len(errors)} error(s)"
