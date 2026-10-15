from app.gen.oj.v1 import judge_pb2, types_pb2
from app.services import LanguageService, StatusService


async def test_status_healthy(dao, queue):
    queue.depth, queue.consumers = 4, 3
    res = await StatusService(dao, queue).get_status(judge_pb2.GetStatusRequest())
    assert res == judge_pb2.GetStatusResponse(healthy=True, dao="ok", broker="ok", queue_depth=4, runners=3)


async def test_status_reports_down_dependencies(dao, queue):
    dao.down = queue.down = True
    res = await StatusService(dao, queue).get_status(judge_pb2.GetStatusRequest())
    assert not res.healthy
    assert res.dao.startswith("error: dao unavailable")
    assert res.broker.startswith("error: RabbitMQ unavailable")
    assert (res.queue_depth, res.runners) == (0, 0)


async def test_status_broker_only_down(dao, queue):
    queue.down = True
    res = await StatusService(dao, queue).get_status(judge_pb2.GetStatusRequest())
    assert (res.healthy, res.dao) == (False, "ok")


async def test_languages():
    res = await LanguageService().list_languages(judge_pb2.ListLanguagesRequest())
    assert [(lang.language, lang.name) for lang in res.languages] == [
        (types_pb2.LANGUAGE_PYTHON, "Python 3"),
        (types_pb2.LANGUAGE_C, "C17 (gcc)"),
        (types_pb2.LANGUAGE_CPP, "C++17 (g++)"),
        (types_pb2.LANGUAGE_JAVASCRIPT, "JavaScript (Node.js)"),
    ]
