from kernel.dependency_policy import are_dependencies_satisfied


class TestDependencyPolicy:
    def test_no_dependencies_are_ready(self):
        assert are_dependencies_satisfied([], []) is True

    def test_all_dependencies_satisfied_are_ready(self):
        assert are_dependencies_satisfied(["A", "B"], ["A", "B"]) is True

    def test_pending_dependency_blocks(self):
        assert are_dependencies_satisfied(["A", "B"], ["A"]) is False

    def test_unrelated_satisfied_task_does_not_count(self):
        assert are_dependencies_satisfied(["A"], ["B"]) is False
