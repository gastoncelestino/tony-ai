import pytest

from kernel.task_graph import (
    TaskGraphProposal,
    TaskGraphProposalError,
    TaskProposal,
)


def test_proposal_becomes_canonical_task_set():
    proposal = TaskGraphProposal.from_iterable(
        [
            TaskProposal("T1", "prepare", "apply"),
            TaskProposal("T2", "implement", "apply", ("T1",)),
        ]
    )

    task_set = proposal.to_task_set()

    assert [task["id"] for task in task_set.tasks] == ["T1", "T2"]
    assert task_set.ready_tasks() == (task_set.tasks[0],)


def test_empty_proposal_is_rejected():
    with pytest.raises(TaskGraphProposalError):
        TaskGraphProposal.from_iterable([]).to_task_set()


def test_duplicate_ids_are_rejected():
    proposal = TaskGraphProposal.from_iterable(
        [
            TaskProposal("T1", "one", "apply"),
            TaskProposal("T1", "two", "apply"),
        ]
    )

    with pytest.raises(TaskGraphProposalError):
        proposal.to_task_set()


def test_unknown_dependency_is_rejected_by_canonical_task_set():
    proposal = TaskGraphProposal.from_iterable(
        [TaskProposal("T1", "one", "apply", ("missing",))]
    )

    with pytest.raises(TaskGraphProposalError):
        proposal.to_task_set()


def test_cycle_is_rejected_by_canonical_task_set():
    proposal = TaskGraphProposal.from_iterable(
        [
            TaskProposal("T1", "one", "apply", ("T2",)),
            TaskProposal("T2", "two", "apply", ("T1",)),
        ]
    )

    with pytest.raises(TaskGraphProposalError):
        proposal.to_task_set()


def test_task_count_limit_is_hard():
    proposal = TaskGraphProposal.from_iterable(
        [TaskProposal("T1", "one", "apply")], max_tasks=0
    )

    with pytest.raises(TaskGraphProposalError):
        proposal.to_task_set()
