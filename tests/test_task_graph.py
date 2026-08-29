import pytest

from kernel.task_graph import (
    TaskGraphProposal,
    TaskGraphProposalError,
    TaskProposal,
)


def task(task_id, description="work", phase="apply", dependencies=(), files=(), objective="do one thing", expected_result="one observable result", verification="run the task test"):
    return TaskProposal(
        task_id,
        description,
        phase,
        dependencies,
        files,
        objective,
        expected_result,
        verification,
    )


def test_proposal_becomes_canonical_task_set():
    proposal = TaskGraphProposal.from_iterable(
        [
            task("T1", "prepare"),
            task("T2", "implement", dependencies=("T1",)),
        ]
    )

    task_set = proposal.to_task_set()

    assert [item["id"] for item in task_set.tasks] == ["T1", "T2"]
    assert task_set.tasks[0]["objective"] == "do one thing"
    assert task_set.ready_tasks() == (task_set.tasks[0],)


def test_empty_proposal_is_rejected():
    with pytest.raises(TaskGraphProposalError):
        TaskGraphProposal.from_iterable([]).to_task_set()


def test_duplicate_ids_are_rejected():
    proposal = TaskGraphProposal.from_iterable([task("T1"), task("T1")])

    with pytest.raises(TaskGraphProposalError):
        proposal.to_task_set()


def test_unknown_dependency_is_rejected_by_canonical_task_set():
    proposal = TaskGraphProposal.from_iterable(
        [task("T1", dependencies=("missing",))]
    )

    with pytest.raises(TaskGraphProposalError):
        proposal.to_task_set()


def test_cycle_is_rejected_by_canonical_task_set():
    proposal = TaskGraphProposal.from_iterable(
        [
            task("T1", dependencies=("T2",)),
            task("T2", dependencies=("T1",)),
        ]
    )

    with pytest.raises(TaskGraphProposalError):
        proposal.to_task_set()


def test_task_count_limit_is_hard():
    proposal = TaskGraphProposal.from_iterable([task("T1")], max_tasks=0)

    with pytest.raises(TaskGraphProposalError):
        proposal.to_task_set()


@pytest.mark.parametrize("field", ["objective", "expected_result", "verification"])
def test_atomic_task_requires_explicit_contract(field):
    values = {
        "objective": "do one thing",
        "expected_result": "one observable result",
        "verification": "run the task test",
    }
    values[field] = ""

    proposal = TaskGraphProposal.from_iterable(
        [task("T1", objective=values["objective"], expected_result=values["expected_result"], verification=values["verification"])]
    )

    with pytest.raises(TaskGraphProposalError, match=field.replace("_", " ")):
        proposal.to_task_set()
