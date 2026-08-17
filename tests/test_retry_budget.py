import unittest

from kernel.retry_budget import RetryBudget


class RetryBudgetTests(unittest.TestCase):
    def test_first_attempt_is_implementation(self):
        budget = RetryBudget(max_attempts=3)

        self.assertEqual(budget.next_action(), "implement")
        self.assertEqual(budget.attempts, 1)
        self.assertFalse(budget.exhausted)
        self.assertEqual(budget.remaining, 2)

    def test_follow_up_attempts_are_targeted_fixes(self):
        budget = RetryBudget(max_attempts=3)

        self.assertEqual(budget.next_action(), "implement")
        self.assertEqual(budget.next_action(), "targeted_fix")
        self.assertEqual(budget.next_action(), "targeted_fix")
        self.assertTrue(budget.exhausted)
        self.assertEqual(budget.remaining, 0)

    def test_exhausted_budget_requires_human(self):
        budget = RetryBudget(max_attempts=3)

        for _ in range(3):
            budget.next_action()

        self.assertEqual(budget.next_action(), "human_required")
        self.assertEqual(budget.attempts, 3)
        self.assertTrue(budget.exhausted)

    def test_budgets_are_independent_by_task(self):
        budget_a = RetryBudget(max_attempts=2)
        budget_b = RetryBudget(max_attempts=2)

        self.assertEqual(budget_a.next_action(), "implement")
        self.assertEqual(budget_b.next_action(), "implement")
        self.assertEqual(budget_a.next_action(), "targeted_fix")
        self.assertTrue(budget_a.exhausted)
        self.assertFalse(budget_b.exhausted)

    def test_reset_restores_budget(self):
        budget = RetryBudget(max_attempts=2)

        budget.next_action()
        budget.next_action()
        self.assertTrue(budget.exhausted)

        budget.reset()

        self.assertEqual(budget.attempts, 0)
        self.assertEqual(budget.remaining, 2)
        self.assertFalse(budget.exhausted)
        self.assertEqual(budget.next_action(), "implement")


if __name__ == "__main__":
    unittest.main()
