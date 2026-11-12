import unittest

from helpers import lab, scripted, sibling

from common import fixtures

harness = sibling("06_harness", "harness")
hx = sibling("06_harness", "hx_tools")


class LoopTest(unittest.TestCase):
    def test_self_correction(self):
        m = lab("06_harness", "declarative")
        events = list(m.make_harness([]).run("q"))
        results = [e for e in events if e["kind"] == "tool_result"]
        self.assertEqual([r["ok"] for r in results], [False, True])
        self.assertIn("PieChart", results[0]["content"])
        self.assertIn("row 2 has 2 cells", results[0]["content"])
        self.assertEqual(events[-1], {"kind": "done", "steps": 3})
        self.assertEqual(sum(1 for e in events if e["kind"] == "render"), 1)

    def test_steps_are_bounded(self):
        always_bad = scripted(lambda msgs: {"tool_calls": [{"name": "render_ui", "arguments": {"spec": {"type": "Nope"}}}]})
        h = harness.Harness(always_bad, [hx.make_render_ui(False)], "s", [])
        events = list(h.run("q"))
        self.assertEqual(events[-1]["kind"], "error")
        self.assertEqual(sum(1 for e in events if e["kind"] == "tool_call"), harness.MAX_STEPS)

    def test_failures_are_results(self):
        h = harness.Harness(scripted([]), [hx.SHOW_COMPONENT], "s", [])
        self.assertEqual(h.execute({"name": "nope", "arguments": "{}"})[1], False)
        self.assertIn("not valid JSON", h.execute({"name": "show_component", "arguments": "{"})[0])
        self.assertIn("needs props", h.execute({"name": "show_component", "arguments": '{"name": "SolarChart", "props": {}}'})[0])

    def test_static_components(self):
        m = lab("06_harness", "static")
        events = list(m.make_harness([]).run("q"))
        self.assertEqual([e["component"] for e in events if e["kind"] == "render"], ["EnergySummary", "SolarChart", "ChargePlan"])

    def test_open_ended_artifact_and_action(self):
        m = lab("06_harness", "open_ended")
        h = m.make_harness([])
        events = list(h.run("q"))
        html = next(e for e in events if e["kind"] == "html")
        self.assertTrue(html["artifact"].startswith("labs/06_harness/out/artifacts/"))
        after = list(h.inject_action("schedule_ev_charge", {"window": "10:30-15:00"}))
        self.assertTrue(any(e["kind"] == "notice" for e in after))
        self.assertEqual(list(h.inject_action("rm_rf", {}))[0]["kind"], "error")

    def test_mixed_patches_owned_state(self):
        m = lab("06_harness", "mixed")
        h = m.make_harness([])
        list(h.run("q"))
        after = [e for e in h.inject_action("schedule_ev_charge", {"window": "10:30-15:00"}) if e["kind"] == "render"]
        self.assertEqual(after[-1]["tree"]["children"][1]["props"]["variant"], "success")

    def test_terminal_and_web_surfaces_see_the_same_ui(self):
        lines, web = [], harness.WebSurface()
        h = harness.Harness(scripted([{"tool_calls": [{"name": "render_ui", "arguments": {"spec": fixtures.dashboard_tree()}}]}, {"text": "ok"}]),
                            [hx.make_render_ui(False)], "s", [harness.TerminalSurface(lines.append), web])
        list(h.run("q"))
        self.assertEqual(web.events[0]["tree"], fixtures.dashboard_tree())
        self.assertTrue(any("YOUR SOLAR WEEK" in line for line in lines))

    def test_web_sessions(self):
        m = lab("06_harness", "mixed")
        events = list(m.http({}, sub=""))
        session = events[0]["id"]
        follow = list(m.http({"session": session, "action": "schedule_ev_charge", "params": {"window": "10:30-15:00"}}, sub="action"))
        self.assertEqual(follow[0]["kind"], "action")
        self.assertEqual(list(m.http({"session": "nope", "action": "x"}, sub="action"))[0]["kind"], "error")


if __name__ == "__main__":
    unittest.main()
