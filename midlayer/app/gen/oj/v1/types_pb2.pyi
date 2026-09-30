import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Language(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    LANGUAGE_UNSPECIFIED: _ClassVar[Language]
    LANGUAGE_PYTHON: _ClassVar[Language]
    LANGUAGE_C: _ClassVar[Language]
    LANGUAGE_CPP: _ClassVar[Language]
    LANGUAGE_JAVASCRIPT: _ClassVar[Language]

class Difficulty(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    DIFFICULTY_UNSPECIFIED: _ClassVar[Difficulty]
    DIFFICULTY_EASY: _ClassVar[Difficulty]
    DIFFICULTY_MEDIUM: _ClassVar[Difficulty]
    DIFFICULTY_HARD: _ClassVar[Difficulty]

class SubmissionStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    SUBMISSION_STATUS_UNSPECIFIED: _ClassVar[SubmissionStatus]
    SUBMISSION_STATUS_PENDING: _ClassVar[SubmissionStatus]
    SUBMISSION_STATUS_JUDGING: _ClassVar[SubmissionStatus]
    SUBMISSION_STATUS_FINISHED: _ClassVar[SubmissionStatus]
    SUBMISSION_STATUS_FAILED: _ClassVar[SubmissionStatus]

class Verdict(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    VERDICT_UNSPECIFIED: _ClassVar[Verdict]
    VERDICT_ACCEPTED: _ClassVar[Verdict]
    VERDICT_WRONG_ANSWER: _ClassVar[Verdict]
    VERDICT_TIME_LIMIT_EXCEEDED: _ClassVar[Verdict]
    VERDICT_MEMORY_LIMIT_EXCEEDED: _ClassVar[Verdict]
    VERDICT_OUTPUT_LIMIT_EXCEEDED: _ClassVar[Verdict]
    VERDICT_RUNTIME_ERROR: _ClassVar[Verdict]
    VERDICT_COMPILATION_ERROR: _ClassVar[Verdict]
    VERDICT_INTERNAL_ERROR: _ClassVar[Verdict]

class RunStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    RUN_STATUS_UNSPECIFIED: _ClassVar[RunStatus]
    RUN_STATUS_OK: _ClassVar[RunStatus]
    RUN_STATUS_TIME_LIMIT_EXCEEDED: _ClassVar[RunStatus]
    RUN_STATUS_MEMORY_LIMIT_EXCEEDED: _ClassVar[RunStatus]
    RUN_STATUS_OUTPUT_LIMIT_EXCEEDED: _ClassVar[RunStatus]
    RUN_STATUS_RUNTIME_ERROR: _ClassVar[RunStatus]
    RUN_STATUS_COMPILATION_ERROR: _ClassVar[RunStatus]
LANGUAGE_UNSPECIFIED: Language
LANGUAGE_PYTHON: Language
LANGUAGE_C: Language
LANGUAGE_CPP: Language
LANGUAGE_JAVASCRIPT: Language
DIFFICULTY_UNSPECIFIED: Difficulty
DIFFICULTY_EASY: Difficulty
DIFFICULTY_MEDIUM: Difficulty
DIFFICULTY_HARD: Difficulty
SUBMISSION_STATUS_UNSPECIFIED: SubmissionStatus
SUBMISSION_STATUS_PENDING: SubmissionStatus
SUBMISSION_STATUS_JUDGING: SubmissionStatus
SUBMISSION_STATUS_FINISHED: SubmissionStatus
SUBMISSION_STATUS_FAILED: SubmissionStatus
VERDICT_UNSPECIFIED: Verdict
VERDICT_ACCEPTED: Verdict
VERDICT_WRONG_ANSWER: Verdict
VERDICT_TIME_LIMIT_EXCEEDED: Verdict
VERDICT_MEMORY_LIMIT_EXCEEDED: Verdict
VERDICT_OUTPUT_LIMIT_EXCEEDED: Verdict
VERDICT_RUNTIME_ERROR: Verdict
VERDICT_COMPILATION_ERROR: Verdict
VERDICT_INTERNAL_ERROR: Verdict
RUN_STATUS_UNSPECIFIED: RunStatus
RUN_STATUS_OK: RunStatus
RUN_STATUS_TIME_LIMIT_EXCEEDED: RunStatus
RUN_STATUS_MEMORY_LIMIT_EXCEEDED: RunStatus
RUN_STATUS_OUTPUT_LIMIT_EXCEEDED: RunStatus
RUN_STATUS_RUNTIME_ERROR: RunStatus
RUN_STATUS_COMPILATION_ERROR: RunStatus

class Problem(_message.Message):
    __slots__ = ("id", "slug", "title", "statement", "difficulty", "time_limit_ms", "memory_limit_mb", "create_time")
    ID_FIELD_NUMBER: _ClassVar[int]
    SLUG_FIELD_NUMBER: _ClassVar[int]
    TITLE_FIELD_NUMBER: _ClassVar[int]
    STATEMENT_FIELD_NUMBER: _ClassVar[int]
    DIFFICULTY_FIELD_NUMBER: _ClassVar[int]
    TIME_LIMIT_MS_FIELD_NUMBER: _ClassVar[int]
    MEMORY_LIMIT_MB_FIELD_NUMBER: _ClassVar[int]
    CREATE_TIME_FIELD_NUMBER: _ClassVar[int]
    id: int
    slug: str
    title: str
    statement: str
    difficulty: Difficulty
    time_limit_ms: int
    memory_limit_mb: int
    create_time: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., slug: _Optional[str] = ..., title: _Optional[str] = ..., statement: _Optional[str] = ..., difficulty: _Optional[_Union[Difficulty, str]] = ..., time_limit_ms: _Optional[int] = ..., memory_limit_mb: _Optional[int] = ..., create_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class TestCase(_message.Message):
    __slots__ = ("id", "problem_id", "input", "expected_output", "is_sample", "ordinal")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    INPUT_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_OUTPUT_FIELD_NUMBER: _ClassVar[int]
    IS_SAMPLE_FIELD_NUMBER: _ClassVar[int]
    ORDINAL_FIELD_NUMBER: _ClassVar[int]
    id: int
    problem_id: int
    input: str
    expected_output: str
    is_sample: bool
    ordinal: int
    def __init__(self, id: _Optional[int] = ..., problem_id: _Optional[int] = ..., input: _Optional[str] = ..., expected_output: _Optional[str] = ..., is_sample: _Optional[bool] = ..., ordinal: _Optional[int] = ...) -> None: ...

class Sample(_message.Message):
    __slots__ = ("input", "output")
    INPUT_FIELD_NUMBER: _ClassVar[int]
    OUTPUT_FIELD_NUMBER: _ClassVar[int]
    input: str
    output: str
    def __init__(self, input: _Optional[str] = ..., output: _Optional[str] = ...) -> None: ...

class TestResult(_message.Message):
    __slots__ = ("test", "verdict", "time_ms", "memory_kb", "sample")
    TEST_FIELD_NUMBER: _ClassVar[int]
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    TIME_MS_FIELD_NUMBER: _ClassVar[int]
    MEMORY_KB_FIELD_NUMBER: _ClassVar[int]
    SAMPLE_FIELD_NUMBER: _ClassVar[int]
    test: int
    verdict: Verdict
    time_ms: int
    memory_kb: int
    sample: bool
    def __init__(self, test: _Optional[int] = ..., verdict: _Optional[_Union[Verdict, str]] = ..., time_ms: _Optional[int] = ..., memory_kb: _Optional[int] = ..., sample: _Optional[bool] = ...) -> None: ...

class Submission(_message.Message):
    __slots__ = ("id", "problem_id", "username", "language", "source", "status", "verdict", "passed", "total", "time_ms", "message", "results", "create_time", "update_time")
    ID_FIELD_NUMBER: _ClassVar[int]
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    PASSED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    TIME_MS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    CREATE_TIME_FIELD_NUMBER: _ClassVar[int]
    UPDATE_TIME_FIELD_NUMBER: _ClassVar[int]
    id: int
    problem_id: int
    username: str
    language: Language
    source: str
    status: SubmissionStatus
    verdict: Verdict
    passed: int
    total: int
    time_ms: int
    message: str
    results: _containers.RepeatedCompositeFieldContainer[TestResult]
    create_time: _timestamp_pb2.Timestamp
    update_time: _timestamp_pb2.Timestamp
    def __init__(self, id: _Optional[int] = ..., problem_id: _Optional[int] = ..., username: _Optional[str] = ..., language: _Optional[_Union[Language, str]] = ..., source: _Optional[str] = ..., status: _Optional[_Union[SubmissionStatus, str]] = ..., verdict: _Optional[_Union[Verdict, str]] = ..., passed: _Optional[int] = ..., total: _Optional[int] = ..., time_ms: _Optional[int] = ..., message: _Optional[str] = ..., results: _Optional[_Iterable[_Union[TestResult, _Mapping]]] = ..., create_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., update_time: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ...) -> None: ...

class ErrorResponse(_message.Message):
    __slots__ = ("error", "details")
    ERROR_FIELD_NUMBER: _ClassVar[int]
    DETAILS_FIELD_NUMBER: _ClassVar[int]
    error: str
    details: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, error: _Optional[str] = ..., details: _Optional[_Iterable[str]] = ...) -> None: ...
