import unittest

from kernel.retry_budget import RetryBudget


class RetryBudgetTests(unittest.TestCase):
    def test_first_attempt_is_implementation(self):
        budget = RetryBudget()

        self.assertEqual(budget.get_next_action("implementation", "task-1"), "implement")
        result = budget.record_attempt("implementation", "task-1", success=False)

        self.assertEqual(result["attempt"], 1)
        self.assertEqual(result["next_action"], "targeted_fix")
        self.assertEqual(budget.get_status("implementation", "task-1")["remaining"], 2)

    def test_follow_up_attempts_are_targeted_fixes(self):
        budget = RetryBudget()

        budget.record_attempt("implementation", "task-1", success=False)
        self.assertEqual(budget.get_next_action("implementation", "task-1"), "targeted_fix")

        budget.record_attempt("implementation", "task-1", success=False)
        self.assertEqual(budget.get_next_action("implementation", "task-1"), "targeted_fix")

    def test_exhausted_budget_requires_human(self):
        budget = RetryBudget()

        for _ in range(3):
            budget.record_attempt("implementation", "task-1", success=False)

        status = budget.get_status("implementation", "task-1")
        self.assertEqual(budget.get_next_action("implementation", "task-1"), "human_required")
        self.assertTrue(status["exhausted"])
        self.assertEqual(status["remaining"], 0)

    def test_budgets_are_independent_by_task(self):
        budget = RetryBudget()

        budget.record_attempt("implementation", "task-a", success=False)
        budget.record_attempt("implementation", "task-a", success=False)
        budget.record_attempt("implementation", "task-a", success=False)

        self.assertEqual(budget.get_next_action("implementation", "task-a"), "human_required")
        self.assertEqual(budget.get_next_action("implementation", "task-b"), "implement")

    def test_reset_restores_budget(self):
        budget = RetryBudget()
        phase, task = "implementation", "task-1"

        budget.record_attempt(phase, task, success=False)
        budget.record_attempt(phase, task, success=False)
        budget.reset(phase, task)

        status = budget.get_status(phase, task)
        self.assertEqual(status["attempts_used"], 0)
        self.assertEqual(status["remaining"], 3)
        self.assertFalse(status["exhausted"])
        self.assertEqual(budget.get_next_action(phase, task), "implement")


if __name__ == "__main__":
    unittest.main()
