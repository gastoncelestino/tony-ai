"""Task-graph aware orchestration facade.

The Task State Graph is authoritative for task transitions. The legacy
TaskLedger is maintained as a compatibility projection for existing callers.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Callable, Mapping, Sequence

from .evidence_state import EvidenceAssessment
from .orchestrator_integration import KernelOrchestrator, OrchestrationDecision, OrchestrationResult
from .quality_gates import QualityGateEvaluation, QualityGatePolicy
from .retrieval_decision import RetrievalAction, RetrievalArbitration, arbitrate_retrieval
from .retrieval_policy import RetrievalDecision, retrieve_until_sufficient
from .runtime_evidence import execution_result_to_evidence
from .runtime_executor import RuntimeExecutionResult, RuntimeExecutor
from .runtime_policy import RuntimePolicy
from .runtime_policy_binding import RuntimePolicyBinding
from .runtime_guard import RuntimeAuthorization
from .schemas import Evidence, TaskStatus
from .task_graph import TaskGraphError, TaskStateGraph
from .task_graph_adapter import _evidence_ref, graph_to_ledger, ledger_to_graph


class TaskGraphKernelOrchestrator(KernelOrchestrator):
    """Kernel orchestrator whose task-state authority is the DAG."""

    def __init__(self, *args, quality_gate_policy: QualityGatePolicy | None = None,
                 runtime_policy: RuntimePolicy | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.task_graph = TaskStateGraph()
        self.quality_gate_policy = quality_gate_policy or QualityGatePolicy()
        self.runtime_policy = RuntimePolicyBinding(runtime_policy)

    def _project_ledger(self) -> None:
        self.task_ledger = graph_to_ledger(self.task_graph, self.task_ledger)

    def authorize_tool(self, tool: str) -> RuntimeAuthorization:
        return self.runtime_policy.authorize_tool(tool)

    def authorize_path(self, path: str) -> RuntimeAuthorization:
        return self.runtime_policy.authorize_path(path)

    def authorize_command(self, command: str) -> RuntimeAuthorization:
        return self.runtime_policy.authorize_command(command)

    def authorize_network(self) -> RuntimeAuthorization:
        return self.runtime_policy.authorize_network()

    def add_task(self, task_id: str, description: str, phase: str,
                 dependencies: tuple = (), files: tuple = ()) -> None:
        super().add_task(task_id, description, phase, dependencies, files)
        self.task_graph = ledger_to_graph(self.task_ledger)

    def start_task(self, task_id: str) -> bool:
        try:
            self.task_graph = self.task_graph.start(task_id)
            self._project_ledger()
            return True
        except TaskGraphError:
            return False

    def assess_task_evidence(self, task_id: str, evidence: Sequence[Evidence], *,
                             minimum_valid: int = 1, minimum_confidence: float = 0.75,
                             confidence: float | None = None) -> EvidenceAssessment:
        node = self.task_graph.get(task_id)
        if node is None:
            raise TaskGraphError(f"Unknown task: {task_id}")
        refs = tuple(_evidence_ref(item) for item in evidence)
        _, assessment = self.task_graph.assess_completion_evidence(
            task_id, evidence, refs, minimum_valid=minimum_valid,
            minimum_confidence=minimum_confidence, confidence=confidence,
        )
        return assessment

    def arbitrate_retrieval(self, assessment: EvidenceAssessment) -> RetrievalArbitration:
        """Return the Kernel's deterministic next action for an assessment."""
        return arbitrate_retrieval(assessment)

    def execute_task(self, task_id: str, command: Sequence[str], *,
                     executor: RuntimeExecutor, claim: str | None = None,
                     cwd: str | None = None) -> OrchestrationResult:
        """Execute through the runtime boundary and let its evidence govern completion."""
        node = self.task_graph.get(task_id)
        if node is None:
            raise TaskGraphError(f"Unknown task: {task_id}")
        if node.status != TaskStatus.IN_PROGRESS:
            raise TaskGraphError(f"Task {task_id} is not in progress")
        result: RuntimeExecutionResult = executor.run(command, cwd=cwd)
        evidence = execution_result_to_evidence(
            result, claim=claim or f"Runtime execution for task {task_id}"
        )
        orchestration = self.complete_task(task_id, [evidence])
        return replace(orchestration, metadata={
            **orchestration.metadata,
            "execution_result": result,
            "evidence": evidence,
        })

    def evaluate_quality_gates(self, results: Mapping[str, object], *,
                               paths: Sequence[str] = (), risk: str | None = None) -> QualityGateEvaluation:
        return self.quality_gate_policy.evaluate(results, paths=paths, risk=risk)

    def retrieve_task_evidence(self, task_id: str, retriever: Callable[[int], Sequence[Evidence]], *,
                               max_attempts: int = 2, minimum_valid: int = 1,
                               minimum_confidence: float = 0.75) -> RetrievalDecision:
        node = self.task_graph.get(task_id)
        if node is None:
            raise TaskGraphError(f"Unknown task: {task_id}")
        if node.status != TaskStatus.IN_PROGRESS:
            raise TaskGraphError(f"Task {task_id} is not in progress")
        collected: list[Evidence] = []
        def collect(attempt: int) -> Sequence[Evidence]:
            evidence = tuple(retriever(attempt))
            collected.extend(evidence)
            return evidence
        decision = retrieve_until_sufficient(collect, max_attempts=max_attempts,
            minimum_valid=minimum_valid, minimum_confidence=minimum_confidence)
        arbitration = arbitrate_retrieval(decision.assessment)
        if arbitration.action is RetrievalAction.TRANSITION:
            refs = tuple(_evidence_ref(item) for item in collected)
            self.task_graph = self.task_graph.complete(task_id, refs)
            existing = self.task_ledger.tasks[task_id]
            self.task_ledger = self.task_ledger.__class__(tasks={**self.task_ledger.tasks,
                task_id: replace(existing, evidence=tuple(collected))})
            self._project_ledger()
        return replace(decision, assessment=arbitration.assessment)

    def complete_task(self, task_id: str, evidence: list = None) -> OrchestrationResult:
        node = self.task_graph.get(task_id)
        if node is None:
            return OrchestrationResult(decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Task {task_id} not found", current_phase=self.change_state.current_phase.value)
        if node.status != TaskStatus.IN_PROGRESS:
            return OrchestrationResult(decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Task {task_id} is not in progress", current_phase=self.change_state.current_phase.value)
        validated_evidence, invalid_evidence = self._validate_evidence_items(evidence or [])
        if invalid_evidence:
            reasons = [f"{type(ev).__name__}: {status}" for ev, status in invalid_evidence[:3]]
            return OrchestrationResult(decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Invalid evidence for task {task_id}: {', '.join(reasons)}",
                current_phase=self.change_state.current_phase.value,
                missing_evidence=tuple(str(e) for e, _ in invalid_evidence[:5]))
        if not validated_evidence:
            return OrchestrationResult(decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"No valid evidence provided for task {task_id}", current_phase=self.change_state.current_phase.value)
        refs = tuple(_evidence_ref(e) for e in validated_evidence)
        self.task_graph, assessment = self.task_graph.assess_completion_evidence(task_id, validated_evidence, refs)
        if not assessment.can_progress:
            return OrchestrationResult(decision=OrchestrationDecision.BLOCK_EVIDENCE_REQUIRED,
                reason=f"Evidence assessment for task {task_id}: {assessment.state.value} — {assessment.reason}",
                current_phase=self.change_state.current_phase.value,
                metadata={"evidence_state": assessment.state.value})
        existing = self.task_ledger.tasks[task_id]
        self.task_ledger = self.task_ledger.__class__(tasks={**self.task_ledger.tasks,
            task_id: replace(existing, evidence=tuple(validated_evidence))})
        self._project_ledger()
        return OrchestrationResult(decision=OrchestrationDecision.PROCEED,
            reason=f"Task {task_id} completed with {len(validated_evidence)} evidence items",
            current_phase=self.change_state.current_phase.value,
            metadata={"task_id": task_id, "evidence_count": len(validated_evidence), "evidence_state": assessment.state.value})

    def fail_task(self, task_id: str, error: str, rollback: dict = None) -> bool:
        try:
            self.task_graph = self.task_graph.fail(task_id, error, rollback=rollback)
            self._project_ledger()
            return True
        except TaskGraphError:
            return False

    def retry_task(self, task_id: str) -> bool:
        try:
            self.task_graph = self.task_graph.retry(task_id)
            self._project_ledger()
            return True
        except TaskGraphError:
            return False

    def rollback_task(self, task_id: str, rollback: dict = None) -> bool:
        try:
            self.task_graph = self.task_graph.rollback_task(task_id, rollback=rollback)
            self._project_ledger()
            return True
        except TaskGraphError:
            return False

    def get_next_task(self) -> dict | None:
        ready = self.task_graph.ready()
        if not ready:
            return None
        node = ready[0]
        return {"id": node.task_id, "description": node.description, "phase": node.phase.value,
                "dependencies": node.dependencies, "files": self.task_ledger.tasks[node.task_id].files}

    def get_task_graph(self) -> TaskStateGraph:
        return self.task_graph

    def get_task_summary(self) -> dict:
        counts = {status.value: 0 for status in TaskStatus}
        for node in self.task_graph.nodes.values():
            counts[node.status.value] += 1
        total = len(self.task_graph.nodes)
        completed = counts[TaskStatus.COMPLETED.value]
        return {"total": total, "completed": completed, "pending": counts[TaskStatus.PENDING.value],
                "in_progress": counts[TaskStatus.IN_PROGRESS.value], "failed": counts[TaskStatus.FAILED.value],
                "blocked": counts[TaskStatus.BLOCKED.value], "completion_rate": completed / total if total else 0.0}


__all__ = ["TaskGraphKernelOrchestrator"]
