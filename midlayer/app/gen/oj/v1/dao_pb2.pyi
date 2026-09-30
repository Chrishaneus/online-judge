import datetime

from google.protobuf import timestamp_pb2 as _timestamp_pb2
from app.gen.oj.v1 import types_pb2 as _types_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ListProblemsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListProblemsResponse(_message.Message):
    __slots__ = ("problems",)
    PROBLEMS_FIELD_NUMBER: _ClassVar[int]
    problems: _containers.RepeatedCompositeFieldContainer[_types_pb2.Problem]
    def __init__(self, problems: _Optional[_Iterable[_Union[_types_pb2.Problem, _Mapping]]] = ...) -> None: ...

class GetProblemRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class GetProblemResponse(_message.Message):
    __slots__ = ("problem",)
    PROBLEM_FIELD_NUMBER: _ClassVar[int]
    problem: _types_pb2.Problem
    def __init__(self, problem: _Optional[_Union[_types_pb2.Problem, _Mapping]] = ...) -> None: ...

class CreateProblemRequest(_message.Message):
    __slots__ = ("problem", "test_cases")
    PROBLEM_FIELD_NUMBER: _ClassVar[int]
    TEST_CASES_FIELD_NUMBER: _ClassVar[int]
    problem: _types_pb2.Problem
    test_cases: _containers.RepeatedCompositeFieldContainer[_types_pb2.TestCase]
    def __init__(self, problem: _Optional[_Union[_types_pb2.Problem, _Mapping]] = ..., test_cases: _Optional[_Iterable[_Union[_types_pb2.TestCase, _Mapping]]] = ...) -> None: ...

class CreateProblemResponse(_message.Message):
    __slots__ = ("problem", "test_cases")
    PROBLEM_FIELD_NUMBER: _ClassVar[int]
    TEST_CASES_FIELD_NUMBER: _ClassVar[int]
    problem: _types_pb2.Problem
    test_cases: _containers.RepeatedCompositeFieldContainer[_types_pb2.TestCase]
    def __init__(self, problem: _Optional[_Union[_types_pb2.Problem, _Mapping]] = ..., test_cases: _Optional[_Iterable[_Union[_types_pb2.TestCase, _Mapping]]] = ...) -> None: ...

class UpdateProblemRequest(_message.Message):
    __slots__ = ("problem",)
    PROBLEM_FIELD_NUMBER: _ClassVar[int]
    problem: _types_pb2.Problem
    def __init__(self, problem: _Optional[_Union[_types_pb2.Problem, _Mapping]] = ...) -> None: ...

class UpdateProblemResponse(_message.Message):
    __slots__ = ("problem",)
    PROBLEM_FIELD_NUMBER: _ClassVar[int]
    problem: _types_pb2.Problem
    def __init__(self, problem: _Optional[_Union[_types_pb2.Problem, _Mapping]] = ...) -> None: ...

class DeleteProblemRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class DeleteProblemResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ListTestCasesRequest(_message.Message):
    __slots__ = ("problem_id", "samples_only")
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    SAMPLES_ONLY_FIELD_NUMBER: _ClassVar[int]
    problem_id: int
    samples_only: bool
    def __init__(self, problem_id: _Optional[int] = ..., samples_only: _Optional[bool] = ...) -> None: ...

class ListTestCasesResponse(_message.Message):
    __slots__ = ("test_cases",)
    TEST_CASES_FIELD_NUMBER: _ClassVar[int]
    test_cases: _containers.RepeatedCompositeFieldContainer[_types_pb2.TestCase]
    def __init__(self, test_cases: _Optional[_Iterable[_Union[_types_pb2.TestCase, _Mapping]]] = ...) -> None: ...

class CreateTestCaseRequest(_message.Message):
    __slots__ = ("test_case",)
    TEST_CASE_FIELD_NUMBER: _ClassVar[int]
    test_case: _types_pb2.TestCase
    def __init__(self, test_case: _Optional[_Union[_types_pb2.TestCase, _Mapping]] = ...) -> None: ...

class CreateTestCaseResponse(_message.Message):
    __slots__ = ("test_case",)
    TEST_CASE_FIELD_NUMBER: _ClassVar[int]
    test_case: _types_pb2.TestCase
    def __init__(self, test_case: _Optional[_Union[_types_pb2.TestCase, _Mapping]] = ...) -> None: ...

class DeleteTestCaseRequest(_message.Message):
    __slots__ = ("problem_id", "id")
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    ID_FIELD_NUMBER: _ClassVar[int]
    problem_id: int
    id: int
    def __init__(self, problem_id: _Optional[int] = ..., id: _Optional[int] = ...) -> None: ...

class DeleteTestCaseResponse(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class CreateSubmissionRequest(_message.Message):
    __slots__ = ("submission",)
    SUBMISSION_FIELD_NUMBER: _ClassVar[int]
    submission: _types_pb2.Submission
    def __init__(self, submission: _Optional[_Union[_types_pb2.Submission, _Mapping]] = ...) -> None: ...

class CreateSubmissionResponse(_message.Message):
    __slots__ = ("submission",)
    SUBMISSION_FIELD_NUMBER: _ClassVar[int]
    submission: _types_pb2.Submission
    def __init__(self, submission: _Optional[_Union[_types_pb2.Submission, _Mapping]] = ...) -> None: ...

class GetSubmissionRequest(_message.Message):
    __slots__ = ("id",)
    ID_FIELD_NUMBER: _ClassVar[int]
    id: int
    def __init__(self, id: _Optional[int] = ...) -> None: ...

class GetSubmissionResponse(_message.Message):
    __slots__ = ("submission",)
    SUBMISSION_FIELD_NUMBER: _ClassVar[int]
    submission: _types_pb2.Submission
    def __init__(self, submission: _Optional[_Union[_types_pb2.Submission, _Mapping]] = ...) -> None: ...

class ListSubmissionsRequest(_message.Message):
    __slots__ = ("problem_id", "username", "statuses", "updated_before", "limit", "offset")
    PROBLEM_ID_FIELD_NUMBER: _ClassVar[int]
    USERNAME_FIELD_NUMBER: _ClassVar[int]
    STATUSES_FIELD_NUMBER: _ClassVar[int]
    UPDATED_BEFORE_FIELD_NUMBER: _ClassVar[int]
    LIMIT_FIELD_NUMBER: _ClassVar[int]
    OFFSET_FIELD_NUMBER: _ClassVar[int]
    problem_id: int
    username: str
    statuses: _containers.RepeatedScalarFieldContainer[_types_pb2.SubmissionStatus]
    updated_before: _timestamp_pb2.Timestamp
    limit: int
    offset: int
    def __init__(self, problem_id: _Optional[int] = ..., username: _Optional[str] = ..., statuses: _Optional[_Iterable[_Union[_types_pb2.SubmissionStatus, str]]] = ..., updated_before: _Optional[_Union[datetime.datetime, _timestamp_pb2.Timestamp, _Mapping]] = ..., limit: _Optional[int] = ..., offset: _Optional[int] = ...) -> None: ...

class ListSubmissionsResponse(_message.Message):
    __slots__ = ("submissions",)
    SUBMISSIONS_FIELD_NUMBER: _ClassVar[int]
    submissions: _containers.RepeatedCompositeFieldContainer[_types_pb2.Submission]
    def __init__(self, submissions: _Optional[_Iterable[_Union[_types_pb2.Submission, _Mapping]]] = ...) -> None: ...

class TestResults(_message.Message):
    __slots__ = ("results",)
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    results: _containers.RepeatedCompositeFieldContainer[_types_pb2.TestResult]
    def __init__(self, results: _Optional[_Iterable[_Union[_types_pb2.TestResult, _Mapping]]] = ...) -> None: ...

class UpdateSubmissionRequest(_message.Message):
    __slots__ = ("id", "status", "verdict", "passed", "total", "time_ms", "message", "results", "expected_statuses")
    ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    VERDICT_FIELD_NUMBER: _ClassVar[int]
    PASSED_FIELD_NUMBER: _ClassVar[int]
    TOTAL_FIELD_NUMBER: _ClassVar[int]
    TIME_MS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    EXPECTED_STATUSES_FIELD_NUMBER: _ClassVar[int]
    id: int
    status: _types_pb2.SubmissionStatus
    verdict: _types_pb2.Verdict
    passed: int
    total: int
    time_ms: int
    message: str
    results: TestResults
    expected_statuses: _containers.RepeatedScalarFieldContainer[_types_pb2.SubmissionStatus]
    def __init__(self, id: _Optional[int] = ..., status: _Optional[_Union[_types_pb2.SubmissionStatus, str]] = ..., verdict: _Optional[_Union[_types_pb2.Verdict, str]] = ..., passed: _Optional[int] = ..., total: _Optional[int] = ..., time_ms: _Optional[int] = ..., message: _Optional[str] = ..., results: _Optional[_Union[TestResults, _Mapping]] = ..., expected_statuses: _Optional[_Iterable[_Union[_types_pb2.SubmissionStatus, str]]] = ...) -> None: ...

class UpdateSubmissionResponse(_message.Message):
    __slots__ = ("submission",)
    SUBMISSION_FIELD_NUMBER: _ClassVar[int]
    submission: _types_pb2.Submission
    def __init__(self, submission: _Optional[_Union[_types_pb2.Submission, _Mapping]] = ...) -> None: ...
