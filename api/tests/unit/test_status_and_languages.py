from app.gen.oj.v1 import judge_pb2, types_pb2
from app.services import LanguageService, StatusService


def test_status_healthy(store, queue):
    queue.depth, queue.consumers = 4, 3
    res = StatusService(store, queue).get_status(judge_pb2.GetStatusRequest())
    assert res == judge_pb2.GetStatusResponse(
        healthy=True, database="ok", broker="ok", queue_depth=4, runners=3
    )


def test_status_reports_down_dependencies(store, queue):
    store.down = queue.down = True
    res = StatusService(store, queue).get_status(judge_pb2.GetStatusRequest())
    assert not res.healthy
    assert res.database.startswith("error: database unavailable")
    assert res.broker.startswith("error: RabbitMQ unavailable")
    assert (res.queue_depth, res.runners) == (0, 0)


def test_status_broker_only_down(store, queue):
    queue.down = True
    res = StatusService(store, queue).get_status(judge_pb2.GetStatusRequest())
    assert (res.healthy, res.database) == (False, "ok")


def test_languages():
    res = LanguageService().list_languages(judge_pb2.ListLanguagesRequest())
    assert [(lang.language, lang.name) for lang in res.languages] == [
        (types_pb2.LANGUAGE_PYTHON, "Python 3"),
        (types_pb2.LANGUAGE_C, "C17 (gcc)"),
        (types_pb2.LANGUAGE_CPP, "C++17 (g++)"),
        (types_pb2.LANGUAGE_JAVASCRIPT, "JavaScript (Node.js)"),
    ]
