import pytest

from app.errors import AlreadyExists, NotFound, ValidationError
from app.gen.oj.v1 import judge_pb2, types_pb2
from app.services import ProblemService
from tests.fakes import seed_problem


@pytest.fixture
def service(dao):
    return ProblemService(dao)


def add_req(**kw):
    req = judge_pb2.AddProblemRequest(slug="double-it", title="Double it", statement="Print 2x.")
    req.test_cases.add(input="1", expected_output="2", is_sample=True)
    req.test_cases.add(input="5", expected_output="10")
    for k, v in kw.items():
        setattr(req, k, v)
    return req


async def test_add_problem_applies_defaults_and_returns_only_samples(service, dao):
    res = await service.add_problem(add_req())
    p = res.problem
    assert p.id > 0
    assert (p.difficulty, p.time_limit_ms, p.memory_limit_mb) == (types_pb2.DIFFICULTY_EASY, 2000, 256)
    assert [(s.input, s.output) for s in p.samples] == [("1", "2")]
    assert [t.ordinal for t in await dao.list_test_cases(p.id)] == [1, 2]


async def test_add_problem_duplicate_slug(service):
    await service.add_problem(add_req())
    with pytest.raises(AlreadyExists):
        await service.add_problem(add_req())


async def test_add_problem_requires_test_cases(service, dao):
    req = add_req()
    del req.test_cases[:]
    with pytest.raises(ValidationError, match="test_cases"):
        await service.add_problem(req)
    assert dao.problems == {}


async def test_get_problem_detail_hides_hidden_tests(service, dao):
    p, _ = await seed_problem(dao)
    res = await service.get_problem_detail(judge_pb2.GetProblemDetailRequest(id=p.id))
    assert res.problem.statement == "Print 2x."
    assert [(s.input, s.output) for s in res.problem.samples] == [("1", "2")]
    with pytest.raises(NotFound):
        await service.get_problem_detail(judge_pb2.GetProblemDetailRequest(id=999))
    with pytest.raises(ValidationError, match="id"):
        await service.get_problem_detail(judge_pb2.GetProblemDetailRequest())


async def test_list_problem_summaries(service, dao):
    await seed_problem(dao, slug="a")
    await seed_problem(dao, slug="b")
    res = await service.list_problem_summaries(judge_pb2.ListProblemSummariesRequest())
    assert [p.slug for p in res.problems] == ["a", "b"]


async def test_edit_problem(service, dao):
    p, _ = await seed_problem(dao)
    req = judge_pb2.EditProblemRequest(
        id=p.id, slug="triple", title="Triple", difficulty=types_pb2.DIFFICULTY_HARD, time_limit_ms=500
    )
    res = await service.edit_problem(req)
    assert (res.problem.slug, res.problem.time_limit_ms, res.problem.memory_limit_mb) == ("triple", 500, 256)
    assert dao.problems[p.id].difficulty == types_pb2.DIFFICULTY_HARD
    with pytest.raises(ValidationError, match="slug"):
        await service.edit_problem(judge_pb2.EditProblemRequest(id=p.id, slug="Bad", title="x"))
    with pytest.raises(NotFound):
        await service.edit_problem(judge_pb2.EditProblemRequest(id=999, slug="x", title="x"))


async def test_remove_problem(service, dao):
    p, _ = await seed_problem(dao)
    await service.remove_problem(judge_pb2.RemoveProblemRequest(id=p.id))
    assert dao.problems == {}
    with pytest.raises(NotFound):
        await service.remove_problem(judge_pb2.RemoveProblemRequest(id=p.id))


async def test_test_case_admin(service, dao):
    p, cases = await seed_problem(dao)
    listed = await service.list_problem_test_cases(judge_pb2.ListProblemTestCasesRequest(problem_id=p.id))
    assert len(listed.test_cases) == 2 and listed.test_cases[1].expected_output == "10"

    added = await service.add_test_case(
        judge_pb2.AddTestCaseRequest(
            problem_id=p.id, test_case=judge_pb2.NewTestCase(input="7", expected_output="14")
        )
    )
    assert (added.test_case.problem_id, added.test_case.ordinal) == (p.id, 3)

    await service.remove_test_case(judge_pb2.RemoveTestCaseRequest(problem_id=p.id, id=cases[0].id))
    with pytest.raises(NotFound):
        await service.remove_test_case(judge_pb2.RemoveTestCaseRequest(problem_id=p.id, id=cases[0].id))
    with pytest.raises(NotFound):
        await service.list_problem_test_cases(judge_pb2.ListProblemTestCasesRequest(problem_id=999))
    with pytest.raises(NotFound):
        await service.add_test_case(judge_pb2.AddTestCaseRequest(problem_id=999))
