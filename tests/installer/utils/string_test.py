from cbs.installer.utils.string import enforce_max_string_length


def test_enforce_max_string_length():
    test_string = "Hello, World!"
    max_length = 8

    assert len(enforce_max_string_length(test_string, max_length)) == max_length
