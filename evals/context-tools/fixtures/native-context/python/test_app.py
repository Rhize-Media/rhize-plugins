from app import run


def test_run() -> None:
    assert run(" Value ") == "value"
