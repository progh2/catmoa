"""패키지 임포트 스모크 테스트."""


def test_import_packages():
    import src
    import src.extract
    import src.gsync
    import src.llm
    import src.parsers
    import src.pipeline
    import src.sources
    import src.ui

    assert src.__version__
