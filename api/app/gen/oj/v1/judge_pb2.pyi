from app.gen.oj.v1 import types_pb2 as _types_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class GetStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetStatusResponse(_message.Message):
    __slots__ = ("healthy", "database", "broker", "queue_depth", "runners")
    HEALTHY_FIELD_NUMBER: _ClassVar[int]
    DATABASE_FIELD_NUMBER: _ClassVar[int]
    BROKER_FIELD_NUMBER: _ClassVar[int]
    QUEUE_DEPTH_FIELD_NUMBER: _ClassVar[int]
    RUNNERS_FIELD_NUMBER: _ClassVar[int]
    healthy: bool
    database: str
    broker: str
    queue_depth: int
    runners: int
    def __init__(self, healthy: _Optional[bool] = ..., database: _Optional[str] = ..., broker: _Optional[str] = ..., queue_depth: _Optional[int] = ..., runners: _Optional[int] = ...) -> None: ...

class LanguageInfo(_message.Message):
    __slots__ = ("language", "name")
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    NAME_FIELD_NUMBER: _ClassVar[int]
    language: _types_pb2.Language
    name: str
    def __init__(self, language: _Optional[_Union[_types_pb2.Language, str]] = ..., name: _Optional[str] = ...) -> None: ...

class ListLanguagesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListLanguagesResponse(_message.Message):
    __slots__ = ("languages",)
    LANGUAGES_FIELD_NUMBER: _ClassVar[int]
    languages: _containers.RepeatedCompositeFieldContainer[LanguageInfo]
    def __init__(self, languages: _Optional[_Iterable[_Union[LanguageInfo, _Mapping]]] = ...) -> None: ...

class ProblemSummary(_message.Message):
    __slots__ = ("id", "slug", "title", "difficulty", "time_limit_ms", "memory_limit_mb")
    ID_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    TIME_LIMIT_MS_FIELD_NUMBER: _ClassVar[int]
    MEMORY_LIMIT_MB_FIELD_NUMBER: _ClassVar[int]
    id: int
    slug: str
    title: str
    difficulty: _types_pb2.Difficulty
    time_limit_ms: int
    memory_limit_mb: int
    def __init__(self, id: _Optional[int] = ..., slug: _Optional[str] = ..., title: _Optional[str] = ..., difficulty: _Optional[_Union[_types_pb2.Difficulty, str]] = ..., time_limit_ms: _Optional[int] = ..., memory_limit_mb: _Optional[int] = ...) -> None: ...

class ProblemDetail(_message.Message):
    __slots__ = ("id", "slug", "title", "difficulty", "time_limit_ms", "memory_limit_mb", "statement", "samples")
    ID_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    TIME_LIMIT_MS_FIELD_NUMBER: _ClassVar[int]
    MEMORY_LIMIT_MB_FIELD_NUMBER: _ClassVar[int]
    STATEMENT_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_FIELD_NUMBER: _ClassVar[int]
    id: int
    slug: str
    title: str
    difficulty: _types_pb2.Difficulty
    time_limit_ms: int
    memory_limit_mb: int
    statement: str
    samples: _containers.RepeatedCompositeFieldContainer[_types_pb2.Sample]
    def __init__(self, id: _Optional[int] = ..., slug: _Optional[str] = ..., title: _Optional[str] = ..., difficulty: _Optional[_Union[_types_pb2.Difficulty, str]] = ..., time_limit_ms: _Optional[int] = ..., memory_limit_mb: _Optional[int] = ..., statement: _Optional[str] = ..., samples: _Optional[_Iterable[_Union[_types_pb2.Sample, _Mapping]]] = ...) -> None: ...

class ListProblemSummariesRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListProblemSummariesResponse(_message.Message):
    __slots__ = ("problems",)
    PROBLEMS_FIELD_NUMBER: _ClassVar[int]
    problems: _containers.RepeatedCompositeFieldContainer[ProblemSummary]
    def __init__(self, problems: _Optional[_Iterable[_Union[ProblemSummary, _Mapping]]] = ...) -> None: ...

class GetProblemDetailRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class GetProblemDetailResponse(_message.Message):
    __slots__ = ("problem",)
    PROBLEM_FIELD_NUMBER: _ClassVar[int]
    problem: ProblemDetail
    def __init__(self, problem: _Optional[_Union[ProblemDetail, _Mapping]] = ...) -> None: ...

class SubmitRequest(_message.Message):
    __slots__ = ("problem_id", "language", "source", "username")
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    problem_id: int
    language: _types_pb2.Language
    source: str
    username: str
    def __init__(self, problem_id: _Optional[int] = ..., language: _Optional[_Union[_types_pb2.Language, str]] = ..., source: _Optional[str] = ..., username: _Optional[str] = ...) -> None: ...

class SubmitResponse(_message.Message):
    __slots__ = ("submission",)
    SUBMISSION_FIELD_NUMBER: _ClassVar[int]
    submission: _types_pb2.Submission
    def __init__(self, submission: _Optional[_Union[_types_pb2.Submission, _Mapping]] = ...) -> None: ...

class ListSubmissionSummariesRequest(_message.Message):
    __slots__ = ("problem_id", "username", "limit", "offset")
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    problem_id: int
    username: str
    limit: int
    offset: int
    def __init__(self, problem_id: _Optional[int] = ..., username: _Optional[str] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListSubmissionSummariesResponse(_message.Message):
    __slots__ = ("submissions",)
    SUBMISSIONS_FIELD_NUMBER: _ClassVar[int]
    submissions: _containers.RepeatedCompositeFieldContainer[_types_pb2.Submission]
    def __init__(self, submissions: _Optional[_Iterable[_Union[_types_pb2.Submission, _Mapping]]] = ...) -> None: ...

class GetSubmissionDetailRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class GetSubmissionDetailResponse(_message.Message):
    __slots__ = ("submission",)
    SUBMISSION_FIELD_NUMBER: _ClassVar[int]
    submission: _types_pb2.Submission
    def __init__(self, submission: _Optional[_Union[_types_pb2.Submission, _Mapping]] = ...) -> None: ...

class RunCodeRequest(_message.Message):
    __slots__ = ("language", "source", "stdin", "problem_id")
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    STDIN_FIELD_NUMBER: _ClassVar[int]
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    language: _types_pb2.Language
    source: str
    stdin: str
    problem_id: int
    def __init__(self, language: _Optional[_Union[_types_pb2.Language, str]] = ..., source: _Optional[str] = ..., stdin: _Optional[str] = ..., problem_id: _Optional[int] = ...) -> None: ...

class RunCodeResponse(_message.Message):
    __slots__ = ("status", "compile_output", "stdout", "stderr", "exit_code", "time_ms", "memory_kb")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    COMPILE_OUTPUT_FIELD_NUMBER: _ClassVar[int]
    STDOUT_FIELD_NUMBER: _ClassVar[int]
    STDERR_FIELD_NUMBER: _ClassVar[int]
    EXIT_CODE_FIELD_NUMBER: _ClassVar[int]
    TIME_MS_FIELD_NUMBER: _ClassVar[int]
    MEMORY_KB_FIELD_NUMBER: _ClassVar[int]
    status: _types_pb2.RunStatus
    compile_output: str
    stdout: str
    stderr: str
    exit_code: int
    time_ms: int
    memory_kb: int
    def __init__(self, status: _Optional[_Union[_types_pb2.RunStatus, str]] = ..., compile_output: _Optional[str] = ..., stdout: _Optional[str] = ..., stderr: _Optional[str] = ..., exit_code: _Optional[int] = ..., time_ms: _Optional[int] = ..., memory_kb: _Optional[int] = ...) -> None: ...

class NewTestCase(_message.Message):
    __slots__ = ("input", "expected_output", "is_sample")
    INPUT_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_OUTPUT_FIELD_NUMBER: _ClassVar[int]
    IS_SAMPLE_FIELD_NUMBER: _ClassVar[int]
    input: str
    expected_output: str
    is_sample: bool
    def __init__(self, input: _Optional[str] = ..., expected_output: _Optional[str] = ..., is_sample: _Optional[bool] = ...) -> None: ...

class AddProblemRequest(_message.Message):
    __slots__ = ("slug", "title", "statement", "difficulty", "time_limit_ms", "memory_limit_mb", "test_cases")
    SLUG_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    STATEMENT_FIELD_NUMBER: _ClassVar[int]
    DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    TIME_LIMIT_MS_FIELD_NUMBER: _ClassVar[int]
    MEMORY_LIMIT_MB_FIELD_NUMBER: _ClassVar[int]
    TEST_CASES_FIELD_NUMBER: _ClassVar[int]
    slug: str
    title: str
    statement: str
    difficulty: _types_pb2.Difficulty
    time_limit_ms: int
    memory_limit_mb: int
    test_cases: _containers.RepeatedCompositeFieldContainer[NewTestCase]
    def __init__(self, slug: _Optional[str] = ..., title: _Optional[str] = ..., statement: _Optional[str] = ..., difficulty: _Optional[_Union[_types_pb2.Difficulty, str]] = ..., time_limit_ms: _Optional[int] = ..., memory_limit_mb: _Optional[int] = ..., test_cases: _Optional[_Iterable[_Union[NewTestCase, _Mapping]]] = ...) -> None: ...

class AddProblemResponse(_message.Message):
    __slots__ = ("problem",)
    PROBLEM_FIELD_NUMBER: _ClassVar[int]
    problem: ProblemDetail
    def __init__(self, problem: _Optional[_Union[ProblemDetail, _Mapping]] = ...) -> None: ...

class EditProblemRequest(_message.Message):
    __slots__ = ("id", "slug", "title", "statement", "difficulty", "time_limit_ms", "memory_limit_mb")
    ID_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    STATEMENT_FIELD_NUMBER: _ClassVar[int]
    DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    TIME_LIMIT_MS_FIELD_NUMBER: _ClassVar[int]
    MEMORY_LIMIT_MB_FIELD_NUMBER: _ClassVar[int]
    id: int
    slug: str
    title: str
    statement: str
    difficulty: _types_pb2.Difficulty
    time_limit_ms: int
    memory_limit_mb: int
    def __init__(self, id: _Optional[int] = ..., slug: _Optional[str] = ..., title: _Optional[str] = ..., statement: _Optional[str] = ..., difficulty: _Optional[_Union[_types_pb2.Difficulty, str]] = ..., time_limit_ms: _Optional[int] = ..., memory_limit_mb: _Optional[int] = ...) -> None: ...

class EditProblemResponse(_message.Message):
    __slots__ = ("problem",)
    PROBLEM_FIELD_NUMBER: _ClassVar[int]
    problem: ProblemSummary
    def __init__(self, problem: _Optional[_Union[ProblemSummary, _Mapping]] = ...) -> None: ...

class RemoveProblemRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class RemoveProblemResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListProblemTestCasesRequest(_message.Message):
    __slots__ = ("problem_id",)
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    problem_id: int
    def __init__(self, problem_id: _Optional[int] = ...) -> None: ...

class ListProblemTestCasesResponse(_message.Message):
    __slots__ = ("test_cases",)
    TEST_CASES_FIELD_NUMBER: _ClassVar[int]
    test_cases: _containers.RepeatedCompositeFieldContainer[_types_pb2.TestCase]
    def __init__(self, test_cases: _Optional[_Iterable[_Union[_types_pb2.TestCase, _Mapping]]] = ...) -> None: ...

class AddTestCaseRequest(_message.Message):
    __slots__ = ("problem_id", "test_case")
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    TEST_CASE_FIELD_NUMBER: _ClassVar[int]
    problem_id: int
    test_case: NewTestCase
    def __init__(self, problem_id: _Optional[int] = ..., test_case: _Optional[_Union[NewTestCase, _Mapping]] = ...) -> None: ...

class AddTestCaseResponse(_message.Message):
    __slots__ = ("test_case",)
    TEST_CASE_FIELD_NUMBER: _ClassVar[int]
    test_case: _types_pb2.TestCase
    def __init__(self, test_case: _Optional[_Union[_types_pb2.TestCase, _Mapping]] = ...) -> None: ...

class RemoveTestCaseRequest(_message.Message):
    __slots__ = ("problem_id", "id")
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    problem_id: int
    id: int
    def __init__(self, problem_id: _Optional[int] = ..., id: _Optional[int] = ...) -> None: ...

class RemoveTestCaseResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
