import app


def test_package_imports() -> None:
    assert app.__version__ == "0.1.0"
