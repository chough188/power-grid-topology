import importlib
import sys
import unittest

from data_loader.synthetic_gen import make_empty_dataset
from tasks_official.contracts import ProblemRecord
from tasks_official.execution import OfficialRunner, SelectionError, build_execution_plan
from tasks_official.gui_controller import OfficialGuiController
from tasks_official.registry import TaskUnavailableError


FORBIDDEN_GUI_IMPORTS = (
    "api",
    "anomaly_detection",
    "correction_engine",
    "data_preprocessing",
    "fastapi",
    "llm_assistant",
    "pandapower",
    "sklearn",
    "torch",
    "uvicorn",
)


class RecordingRegistry:
    def __init__(self, detectors):
        self.detectors = detectors
        self.resolved = []

    def resolve(self, task):
        self.resolved.append(task.code)
        try:
            return self.detectors[task.code]
        except KeyError as error:
            raise TaskUnavailableError(f"missing {task.code}") from error


class SelectedExecutionTests(unittest.TestCase):
    def test_empty_selection_is_rejected(self):
        with self.assertRaises(SelectionError):
            build_execution_plan([])

    def test_only_selected_task_is_resolved_and_executed(self):
        invoked = []

        def task_1_1(context):
            invoked.append("1.1")
            return [ProblemRecord(task_code="1.1", device_id="TMP0001")]

        def task_1_2(context):
            invoked.append("1.2")
            return [ProblemRecord(task_code="1.2", device_id="TMP0002")]

        registry = RecordingRegistry({"1.1": task_1_1, "1.2": task_1_2})
        result = OfficialRunner(registry).run(["1.1"], make_empty_dataset())

        self.assertEqual(registry.resolved, ["1.1"])
        self.assertEqual(invoked, ["1.1"])
        self.assertEqual(result.executed_task_codes, ("1.1",))
        self.assertNotIn("1.2", result.records_by_task)

    def test_preflight_failure_prevents_partial_execution(self):
        invoked = []

        def task_1_1(context):
            invoked.append("1.1")
            return []

        registry = RecordingRegistry({"1.1": task_1_1})
        with self.assertRaises(TaskUnavailableError):
            OfficialRunner(registry).run(["1.1", "1.2"], make_empty_dataset())

        self.assertEqual(registry.resolved, ["1.1", "1.2"])
        self.assertEqual(invoked, [])

    def test_default_registry_resolves_ready_tasks_without_pre_importing(self):
        result = OfficialRunner().run(["1.1"], make_empty_dataset())
        self.assertIn("1.1", result.records_by_task)
        self.assertEqual(result.executed_task_codes, ("1.1",))


class OfficialGuiIsolationTests(unittest.TestCase):
    def test_gui_module_import_does_not_load_forbidden_components(self):
        before = set(sys.modules)
        module = importlib.import_module("tasks_official.gui")
        self.assertTrue(hasattr(module, "OfficialCompetitionGui"))
        new_modules = set(sys.modules) - before
        for component in FORBIDDEN_GUI_IMPORTS:
            self.assertNotIn(component, new_modules,
                f"importing {module.__name__} should not pull in {component}")

    def test_gui_controller_requires_explicit_selection(self):
        with self.assertRaises(SelectionError):
            OfficialGuiController().create_plan([])

    def test_gui_plan_does_not_import_task_modules(self):
        prefix = "tasks_official.group_01_topology.task_1_2_break"
        before = {name for name in sys.modules if name.startswith(prefix)}
        plan = OfficialGuiController().create_plan(["1.2"])
        self.assertEqual(plan.task_codes, ("1.2",))
        after = {name for name in sys.modules if name.startswith(prefix)}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
