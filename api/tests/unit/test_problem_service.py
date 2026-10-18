import pytest

from app.errors import Conflict, NotFound, ValidationError
from app.gen.oj.v1 import judge_pb2, types_pb2
from app.services import ProblemService
from tests.fakes import seed_problem


@pytest.fixture
def service(store):
    return ProblemService(store)


def add_req(**kw):
    req = judge_pb2.AddProblemRequest(slug="double-it", title="Double it", statement="Print 2x.")
    req.test_cases.add(input="1", expected_output="2", is_sample=True)
    req.test_cases.add(input="5", expected_output="10")
    for k, v in kw.items():
        setattr(req, k, v)
    return req


def test_add_problem_applies_defaults_and_returns_only_samples(service, store):
    res = service.add_problem(add_req())
    p = res.problem
    assert p.id > 0
    assert (p.difficulty, p.time_limit_ms, p.memory_limit_mb) == (types_pb2.DIFFICULTY_EASY, 2000, 256)
    assert [(s.input, s.output) for s in p.samples] == [("1", "2")]
    assert [t.ordinal for t in store.list_test_cases(p.id)] == [1, 2]


def test_add_problem_duplicate_slug(service):
    service.add_problem(add_req())
    with pytest.raises(Conflict):
        service.add_problem(add_req())


def test_add_problem_requires_test_cases(service, store):
    req = add_req()
    del req.test_cases[:]
    with pytest.raises(ValidationError, match="test_cases"):
        service.add_problem(req)
    assert store.problems == {}


def test_get_problem_detail_hides_hidden_tests(service, store):
    p, _ = seed_problem(store)
    res = service.get_problem_detail(judge_pb2.GetProblemDetailRequest(id=p.id))
    assert res.problem.statement == "Print 2x."
    assert [(s.input, s.output) for s in res.problem.samples] == [("1", "2")]
    with pytest.raises(NotFound):
        service.get_problem_detail(judge_pb2.GetProblemDetailRequest(id=999))
    with pytest.raises(ValidationError, match="id"):
        service.get_problem_detail(judge_pb2.GetProblemDetailRequest())


def test_list_problem_summaries(service, store):
    seed_problem(store, slug="a")
    seed_problem(store, slug="b")
    res = service.list_problem_summaries(judge_pb2.ListProblemSummariesRequest())
    assert [p.slug for p in res.problems] == ["a", "b"]


def test_edit_problem(service, store):
    p, _ = seed_problem(store)
    req = judge_pb2.EditProblemRequest(
        id=p.id, slug="triple", title="Triple", difficulty=types_pb2.DIFFICULTY_HARD, time_limit_ms=500
    )
    res = service.edit_problem(req)
    assert (res.problem.slug, res.problem.time_limit_ms, res.problem.memory_limit_mb) == ("triple", 500, 256)
    assert store.problems[p.id].difficulty == types_pb2.DIFFICULTY_HARD
    with pytest.raises(ValidationError, match="slug"):
        service.edit_problem(judge_pb2.EditProblemRequest(id=p.id, slug="Bad", title="x"))
    with pytest.raises(NotFound):
        service.edit_problem(judge_pb2.EditProblemRequest(id=999, slug="x", title="x"))


def test_remove_problem(service, store):
    p, _ = seed_problem(store)
    service.remove_problem(judge_pb2.RemoveProblemRequest(id=p.id))
    assert store.problems == {}
    with pytest.raises(NotFound):
        service.remove_problem(judge_pb2.RemoveProblemRequest(id=p.id))


def test_test_case_admin(service, store):
    p, cases = seed_problem(store)
    listed = service.list_problem_test_cases(judge_pb2.ListProblemTestCasesRequest(problem_id=p.id))
    assert len(listed.test_cases) == 2 and listed.test_cases[1].expected_output == "10"

    added = service.add_test_case(
        judge_pb2.AddTestCaseRequest(
            problem_id=p.id, test_case=judge_pb2.NewTestCase(input="7", expected_output="14")
        )
    )
    assert (added.test_case.problem_id, added.test_case.ordinal) == (p.id, 3)

    service.remove_test_case(judge_pb2.RemoveTestCaseRequest(problem_id=p.id, id=cases[0].id))
    with pytest.raises(NotFound):
        service.remove_test_case(judge_pb2.RemoveTestCaseRequest(problem_id=p.id, id=cases[0].id))
    with pytest.raises(NotFound):
        service.list_problem_test_cases(judge_pb2.ListProblemTestCasesRequest(problem_id=999))
    with pytest.raises(NotFound):
        service.add_test_case(judge_pb2.AddTestCaseRequest(problem_id=999))
