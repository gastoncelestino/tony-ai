from kernel.task_execution_policy import can_start_task


class TestTaskExecutionPolicy:
    def test_pending_task_can_start(self):
        assert can_start_task("pending") is True

    def test_running_task_cannot_start_again(self):
        assert can_start_task("running") is False

    def test_completed_task_cannot_start(self):
        assert can_start_task("completed") is False

    def test_unknown_status_is_blocked(self):
        assert can_start_task("unknown") is False
