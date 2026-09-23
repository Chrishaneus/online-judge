import asyncio

import pytest

from app import judge
from app.judge import Judge, evaluate, normalize_output, outputs_match
from tests.fakes import FakeDao, FakeRunner


@pytest.mark.parametrize(
    "actual,expected,ok",
    [
        ("3\n", "3", True),
        ("3", "3\n\n\n", True),
        ("1 2   \r\n3\r\n", "1 2\n3", True),
        ("3\n4", "3\n5", False),
        (" 3", "3", False),  # leading whitespace is significant
        ("", "", True),
        ("a\n\nb", "a\nb", False),  # inner blank lines are significant
    ],
)
def test_outputs_match(actual, expected, ok):
    assert outputs_match(actual, expected) is ok


def test_normalize_output():
    assert normalize_output("x  \n\n") == "x"


TCS = [
    {"id": 10, "expected_output": "2", "is_sample": True},
    {"id": 11, "expected_output": "4", "is_sample": False},
    {"id": 12, "expected_output": "6", "is_sample": False},
]


def runner_resp(*items):
    return {
        "status": "OK",
        "results": [
            {"id": str(tc["id"]), "status": st, "stdout": out, "time_ms": t, "memory_kb": 100}
            for tc, (st, out, t) in zip(TCS, items)
        ],
    }


def test_evaluate_all_accepted():
    o = evaluate(TCS, runner_resp(("OK", "2\n", 5), ("OK", "4", 9), ("OK", "6 ", 7)))
    assert (o.verdict, o.passed, o.total, o.time_ms) == ("AC", 3, 3, 9)
    assert [r["test"] for r in o.results] == [1, 2, 3]
    assert o.results[0]["sample"] is True


def test_evaluate_first_failure_wins():
    o = evaluate(TCS, runner_resp(("OK", "2", 1), ("TLE", "", 1000), ("OK", "nope", 1)))
    assert o.verdict == "TLE"
    assert o.passed == 1
    assert o.message == "Time Limit Exceeded on test 2"
    assert [r["verdict"] for r in o.results] == ["AC", "TLE", "WA"]


def test_evaluate_compile_error():
    o = evaluate(TCS, {"status": "CE", "compile_output": "boom", "results": []})
    assert (o.verdict, o.passed, o.total, o.message) == ("CE", 0, 3, "boom")


def test_evaluate_missing_result_is_internal_error():
    o = evaluate(TCS, {"status": "OK", "results": []})
    assert o.verdict == "IE"


def test_outcome_truncates_message():
    o = judge.Outcome("CE", 0, 1, message="x" * 10_000)
    assert len(o.as_update()["message"]) == judge.MAX_MESSAGE_CHARS


async def _setup(source: str):
    dao, runner = FakeDao(), FakeRunner()
    p = await dao.create_problem({"slug": "d", "title": "Double", "statement": "", "difficulty": "easy",
                                  "time_limit_ms": 1000, "memory_limit_mb": 64})
    for i, (inp, out) in enumerate([("1", "2"), ("5", "10")]):
        await dao.create_testcase(p["id"], {"input": inp, "expected_output": out, "is_sample": i == 0, "ordinal": i})
    sub = await dao.create_submission({"problem_id": p["id"], "language": "python", "source": source, "username": "u"})
    return dao, runner, sub["id"]


@pytest.mark.parametrize(
    "source,verdict,status,passed",
    [
        ("double", "AC", "FINISHED", 2),
        ("echo", "WA", "FINISHED", 0),
        ("tle", "TLE", "FINISHED", 0),
        ("ce", "CE", "FINISHED", 0),
        ("boom", "IE", "FAILED", 0),
    ],
)
def test_judge_end_to_end(source, verdict, status, passed):
    async def go():
        dao, runner, sid = await _setup(source)
        await Judge(dao, runner).judge(sid)
        return dao.submissions[sid]

    sub = asyncio.run(go())
    assert (sub["verdict"], sub["status"], sub["passed"]) == (verdict, status, passed)


def test_judge_skips_finished():
    async def go():
        dao, runner, sid = await _setup("double")
        await dao.update_submission(sid, status="FINISHED", verdict="AC")
        await Judge(dao, runner).judge(sid)
        return runner.calls

    assert asyncio.run(go()) == []


def test_worker_pool_and_recovery():
    async def go():
        dao, runner, sid1 = await _setup("double")
        sub2 = await dao.create_submission({"problem_id": 1, "language": "python", "source": "echo", "username": "u"})
        await dao.update_submission(sub2["id"], status="JUDGING")  # interrupted mid-judge
        j = Judge(dao, runner, workers=2)
        await j.start(recover=True)
        await asyncio.wait_for(j.queue.join(), timeout=5)
        await j.stop()
        return dao.submissions[sid1], dao.submissions[sub2["id"]]

    s1, s2 = asyncio.run(go())
    assert s1["verdict"] == "AC" and s2["verdict"] == "WA"
