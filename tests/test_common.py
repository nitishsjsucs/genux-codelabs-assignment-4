import json
import re
import unittest

from helpers import ROOT  # noqa: F401  (puts the repo on sys.path)

from common import catalog, data, fixtures, jsonpatch, labkit, sandbox, term
from common.llm import ScriptedModel, collect


class DataTest(unittest.TestCase):
    def test_every_day_balances(self):
        for d in data.WEEK:  # use = self-consumed solar + import
            self.assertAlmostEqual(d["use"], d["solar"] - d["export"] + d["import"], places=6, msg=d["day"])

    def test_summary_numbers(self):
        s = data.summary()
        self.assertEqual((s["solar_kwh"], s["use_kwh"], s["import_kwh"]), (133.3, 158.4, 45.9))
        self.assertEqual((s["self_sufficiency_pct"], s["solar_delta_pct"], s["best_window"]), (71, 9, "10:30-15:00"))
        self.assertEqual(s["saving_vs_peak"], 14.02)

    def test_clock_fixture_matches_the_data(self):
        html = fixtures.energy_clock_html()
        self.assertIn(f"{round(sum(data.SOLAR_KW), 1)} kWh solar", html)
        solar = json.loads(re.search(r"const solar=(\[[^\]]*\])", html).group(1))
        self.assertEqual(solar, data.SOLAR_KW)
        self.assertEqual(sandbox.policy_check(html), [])


class JsonPatchTest(unittest.TestCase):
    def test_operations(self):
        doc = {"a": {"b": [1, 2]}}
        doc = jsonpatch.apply_patch(doc, [
            {"op": "add", "path": "/a/b/-", "value": 3},
            {"op": "add", "path": "/a/b/0", "value": 0},
            {"op": "replace", "path": "/a/b/1", "value": 9},
            {"op": "remove", "path": "/a/b/2"},
            {"op": "add", "path": "/x~1y", "value": True},
            {"op": "test", "path": "/x~1y", "value": True},
        ])
        self.assertEqual(doc, {"a": {"b": [0, 9, 3]}, "x/y": True})

    def test_errors(self):
        with self.assertRaises(jsonpatch.PatchError):
            jsonpatch.apply_op({"a": 1}, {"op": "replace", "path": "/missing", "value": 1})
        with self.assertRaises(jsonpatch.PatchError):
            jsonpatch.apply_op({"a": 1}, {"op": "test", "path": "/a", "value": 2})
        with self.assertRaises(jsonpatch.PatchError):
            jsonpatch.apply_op([], {"op": "add", "path": "/5", "value": 1})

    def test_values_are_copied(self):
        value = {"k": [1]}
        doc = jsonpatch.apply_op({}, {"op": "add", "path": "/v", "value": value})
        value["k"].append(2)
        self.assertEqual(doc["v"], {"k": [1]})


class CatalogTest(unittest.TestCase):
    def test_dashboard_fixtures_are_valid(self):
        self.assertEqual(catalog.validate_tree(fixtures.dashboard_tree(), allow_generated=False), [])
        self.assertEqual(catalog.validate_tree(fixtures.dashboard_tree(True, True), allow_generated=True), [])

    def test_generated_view_needs_permission(self):
        errors = catalog.validate_tree(fixtures.dashboard_tree(True, True), allow_generated=False)
        self.assertTrue(any("GeneratedView" in e for e in errors))

    def test_errors_are_specific(self):
        bad = fixtures.node("Column", [
            fixtures.node("Metric", label="x"),
            fixtures.node("BarChart", title="t", labels=["a"], values=[1, 2]),
            fixtures.node("Button", label="Pay", action="transfer_funds"),
            fixtures.node("Text", text="hi", variant="shout"),
        ])
        errors = " | ".join(catalog.validate_tree(bad))
        for needle in ("missing required prop 'value'", "1 labels but 2 values", "'transfer_funds' is not allowed", "must be one of"):
            self.assertIn(needle, errors)

    def test_flat_round_trip(self):
        tree = fixtures.dashboard_tree(with_actions=True)
        back = catalog.flat_to_tree(fixtures.to_flat(tree))
        strip = lambda n: {"type": n["type"], "props": n["props"], "children": [strip(c) for c in n["children"]]}  # noqa: E731
        self.assertEqual(strip(back), strip(tree))


class SandboxTest(unittest.TestCase):
    def test_policy_catches_escapes(self):
        cases = {
            "<img src='https://x.example/a.gif'>": "remote URL",
            "<script>fetch('/x')</script>": "network",
            "<form action='/pay'></form>": "form",
            "<script>localStorage.x=1</script>": "storage",
            "<script>top.location='x'</script>": "parent",
            "<iframe srcdoc='x'></iframe>": "frame",
        }
        for html, word in cases.items():
            self.assertTrue(any(word in p for p in sandbox.policy_check(html)), html)

    def test_csp_goes_first(self):
        doc = sandbox.srcdoc("<!doctype html><script>alert(1)</script>")
        self.assertLess(doc.index("Content-Security-Policy"), doc.index("alert"))
        self.assertIn("connect-src 'none'", doc)
        self.assertTrue(sandbox.srcdoc("<b>x</b>").startswith("<!doctype html><meta http-equiv"))


class LabkitTest(unittest.TestCase):
    def test_action_round_trip(self):
        text = labkit.action_text("schedule_ev_charge", {"window": "10:30-15:00"})
        self.assertEqual(labkit.parse_action(text), ("schedule_ev_charge", {"window": "10:30-15:00"}))
        self.assertIsNone(labkit.parse_action("hello"))

    def test_gate(self):
        with self.assertRaises(PermissionError):
            labkit.check_action("delete_everything", {})
        with self.assertRaises(ValueError):
            labkit.check_action("schedule_ev_charge", {"window": "03:00-04:00"})
        self.assertEqual(labkit.schedule("10:30-15:00")["cost"], 1.10)


class ModelAndTermTest(unittest.TestCase):
    def test_scripted_model_pieces(self):
        model = ScriptedModel([{"text": "hello world", "tool_calls": [{"name": "t", "arguments": {"a": 1}}]}], chunk=4)
        text, calls = collect(model.stream([{"role": "user", "content": "x"}]))
        self.assertEqual(text, "hello world")
        self.assertEqual(calls[0]["name"], "t")
        self.assertEqual(calls[0]["arguments"], '{"a": 1}')

    def test_turn_index_follows_history(self):
        model = ScriptedModel([{"text": "one"}, {"text": "two"}])
        self.assertEqual(collect(model.stream([{"role": "user", "content": "x"}, {"role": "assistant", "content": "one"}]))[0], "two")

    def test_terminal_renderer(self):
        text = term.to_text(fixtures.dashboard_tree(True, True))
        for needle in ("YOUR SOLAR WEEK", "Sat ##############################", "[ Schedule 10:30-15:00 ] -> schedule_ev_charge", "[generated view: Energy clock"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
