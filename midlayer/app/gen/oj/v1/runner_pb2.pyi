from app.gen.oj.v1 import types_pb2 as _types_pb2
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class ExecuteStatus(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    EXECUTE_STATUS_UNSPECIFIED: _ClassVar[ExecuteStatus]
    EXECUTE_STATUS_OK: _ClassVar[ExecuteStatus]
    EXECUTE_STATUS_COMPILATION_ERROR: _ClassVar[ExecuteStatus]
    EXECUTE_STATUS_REJECTED: _ClassVar[ExecuteStatus]
    EXECUTE_STATUS_INTERNAL_ERROR: _ClassVar[ExecuteStatus]
EXECUTE_STATUS_UNSPECIFIED: ExecuteStatus
EXECUTE_STATUS_OK: ExecuteStatus
EXECUTE_STATUS_COMPILATION_ERROR: ExecuteStatus
EXECUTE_STATUS_REJECTED: ExecuteStatus
EXECUTE_STATUS_INTERNAL_ERROR: ExecuteStatus

class ExecuteJob(_message.Message):
    __slots__ = ("job_id", "submission_id", "language", "source", "tests", "time_limit_ms", "memory_limit_mb")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    SUBMISSION_ID_FIELD_NUMBER: _ClassVar[int]
    LANGUAGE_FIELD_NUMBER: _ClassVar[int]
    SOURCE_FIELD_NUMBER: _ClassVar[int]
    TESTS_FIELD_NUMBER: _ClassVar[int]
    TIME_LIMIT_MS_FIELD_NUMBER: _ClassVar[int]
    MEMORY_LIMIT_MB_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    submission_id: int
    language: _types_pb2.Language
    source: str
    tests: _containers.RepeatedCompositeFieldContainer[TestInput]
    time_limit_ms: int
    memory_limit_mb: int
    def __init__(self, job_id: _Optional[str] = ..., submission_id: _Optional[int] = ..., language: _Optional[_Union[_types_pb2.Language, str]] = ..., source: _Optional[str] = ..., tests: _Optional[_Iterable[_Union[TestInput, _Mapping]]] = ..., time_limit_ms: _Optional[int] = ..., memory_limit_mb: _Optional[int] = ...) -> None: ...

class TestInput(_message.Message):
    __slots__ = ("id", "stdin")
    ID_FIELD_NUMBER: _ClassVar[int]
    STDIN_FIELD_NUMBER: _ClassVar[int]
    id: str
    stdin: str
    def __init__(self, id: _Optional[str] = ..., stdin: _Optional[str] = ...) -> None: ...

class ExecuteResult(_message.Message):
    __slots__ = ("status", "compile_output", "results", "error")
    STATUS_FIELD_NUMBER: _ClassVar[int]
    COMPILE_OUTPUT_FIELD_NUMBER: _ClassVar[int]
    RESULTS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    status: ExecuteStatus
    compile_output: str
    results: _containers.RepeatedCompositeFieldContainer[TestRun]
    error: str
    def __init__(self, status: _Optional[_Union[ExecuteStatus, str]] = ..., compile_output: _Optional[str] = ..., results: _Optional[_Iterable[_Union[TestRun, _Mapping]]] = ..., error: _Optional[str] = ...) -> None: ...

class TestRun(_message.Message):
    __slots__ = ("id", "status", "stdout", "stderr", "exit_code", "time_ms", "memory_kb")
    ID_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    STDOUT_FIELD_NUMBER: _ClassVar[int]
    STDERR_FIELD_NUMBER: _ClassVar[int]
    EXIT_CODE_FIELD_NUMBER: _ClassVar[int]
    TIME_MS_FIELD_NUMBER: _ClassVar[int]
    MEMORY_KB_FIELD_NUMBER: _ClassVar[int]
    id: str
    status: _types_pb2.RunStatus
    stdout: str
    stderr: str
    exit_code: int
    time_ms: int
    memory_kb: int
    def __init__(self, id: _Optional[str] = ..., status: _Optional[_Union[_types_pb2.RunStatus, str]] = ..., stdout: _Optional[str] = ..., stderr: _Optional[str] = ..., exit_code: _Optional[int] = ..., time_ms: _Optional[int] = ..., memory_kb: _Optional[int] = ...) -> None: ...

class JobEvent(_message.Message):
    __slots__ = ("job_id", "submission_id", "runner_id", "started", "finished")
    JOB_ID_FIELD_NUMBER: _ClassVar[int]
    SUBMISSION_ID_FIELD_NUMBER: _ClassVar[int]
    RUNNER_ID_FIELD_NUMBER: _ClassVar[int]
    STARTED_FIELD_NUMBER: _ClassVar[int]
    FINISHED_FIELD_NUMBER: _ClassVar[int]
    job_id: str
    submission_id: int
    runner_id: str
    started: JobStarted
    finished: ExecuteResult
    def __init__(self, job_id: _Optional[str] = ..., submission_id: _Optional[int] = ..., runner_id: _Optional[str] = ..., started: _Optional[_Union[JobStarted, _Mapping]] = ..., finished: _Optional[_Union[ExecuteResult, _Mapping]] = ...) -> None: ...

class JobStarted(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...
