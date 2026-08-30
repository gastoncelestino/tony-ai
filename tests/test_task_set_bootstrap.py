import unittest

from kernel.task_set_bootstrap import _parse_tasks


class TaskSetBootstrapParsingTests(unittest.TestCase):
    def test_accepts_complete_task_result_wrapper(self):
        tasks = _parse_tasks(
            '<task_result>{"tasks":[{"id":"one","description":"Inspect one","phase":"explore","dependencies":[],"files":[]}]}</task_result>'
        )
        self.assertEqual(tasks[0]["id"], "one")

    def test_accepts_truncated_task_result_wrapper(self):
        tasks = _parse_tasks(
            '<task_result>{"tasks":[{"id":"one","description":"Inspect one","phase":"explore","dependencies":[],"files":[]}]}'
        )
        self.assertEqual(tasks[0]["description"], "Inspect one")

    def test_accepts_single_file_path_for_compatibility(self):
        tasks = _parse_tasks(
            '<task_result>{"tasks":[{"id":"one","description":"Inspect one","phase":"explore","dependencies":[],"files":"kernel/state.py"}]}</task_result>'
        )
        self.assertEqual(tasks[0]["files"], ("kernel/state.py",))

    def test_rejects_non_json_output(self):
        with self.assertRaises(ValueError):
            _parse_tasks("not a task set")


if __name__ == "__main__":
    unittest.main()
