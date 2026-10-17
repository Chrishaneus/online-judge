"""Supported languages. Static: every runner image ships all of them."""

from app.gen.oj.v1 import judge_pb2, types_pb2

LANGUAGE_NAMES = {
    types_pb2.LANGUAGE_PYTHON: "Python 3",
    types_pb2.LANGUAGE_C: "C17 (gcc)",
    types_pb2.LANGUAGE_CPP: "C++17 (g++)",
    types_pb2.LANGUAGE_JAVASCRIPT: "JavaScript (Node.js)",
}


class LanguageService:
    def list_languages(self, _: judge_pb2.ListLanguagesRequest) -> judge_pb2.ListLanguagesResponse:
        return judge_pb2.ListLanguagesResponse(
            languages=[
                judge_pb2.LanguageInfo(language=lang, name=name) for lang, name in LANGUAGE_NAMES.items()
            ]
        )
