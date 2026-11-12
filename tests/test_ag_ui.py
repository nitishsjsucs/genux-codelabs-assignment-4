import json
import unittest

from helpers import lab, scripted, sibling

from common import catalog, data

agui = sibling("01_ag_ui", "agui")
PROMPT = [{"id": "u1", "role": "user", "content": data.PROMPT}]


class EventShapeTest(unittest.TestCase):
    def test_fields_are_camel_case_and_validated(self):
        e = agui.event("TOOL_CALL_START", toolCallId="c1", toolCallName="x")
        self.assertEqual(agui.validate_event(e), [])
        self.assertEqual(agui.validate_event({"type": "TOOL_CALL_START", "tool_call_id": "c1"}),
                         ["TOOL_CALL_START: missing toolCallId", "TOOL_CALL_START: missing toolCallName"])
        with self.assertRaises(ValueError):
            agui.event("NOT_AN_EVENT")

    def test_sequence_checker_catches_unbalanced_streams(self):
        events = [agui.event("RUN_STARTED", threadId="t", runId="r"),
                  agui.event("TEXT_MESSAGE_START", messageId="m", role="assistant")]
        problems = agui.check_sequence(events)
        self.assertTrue(any("never ended" in p for p in problems))
        self.assertTrue(any("last event" in p for p in problems))


class ModesTest(unittest.TestCase):
    def test_static_ends_the_run_on_client_tools(self):
        m = lab("01_ag_ui", "static")
        events = list(m.run(agui.run_input(PROMPT, tools=m.FRONTEND_TOOLS), scripted(m.SCRIPT)))
        self.assertEqual(agui.check_sequence(events), [])
        names = [e["toolCallName"] for e in events if e["type"] == "TOOL_CALL_START"]
        self.assertEqual(names, ["show_energy_summary", "show_solar_chart", "show_charge_plan"])
        self.assertFalse(any(e["type"] == "TOOL_CALL_RESULT" for e in events), "client tools are not executed by the server")
        for m_ in agui.messages_from_events(events):
            for call in m_.get("toolCalls", []):
                tree = m.component_tree(call["function"]["name"], json.loads(call["function"]["arguments"]))
                self.assertEqual(catalog.validate_tree(tree), [])

    def test_declarative_builds_the_tree_with_deltas(self):
        m = lab("01_ag_ui", "declarative")
        events = list(m.run(agui.run_input(PROMPT, state=m.INITIAL_STATE), scripted(m.SCRIPT)))
        self.assertEqual(agui.check_sequence(events), [])
        deltas = [e for e in events if e["type"] == "STATE_DELTA"]
        self.assertEqual(len(deltas), 11)
        tree = catalog.flat_to_tree(agui.final_state(events)["ui"])
        self.assertEqual(catalog.validate_tree(tree), [])
        self.assertEqual(catalog.count(tree), 12)

    def test_declarative_rejects_bad_components(self):
        m = lab("01_ag_ui", "declarative")
        state = json.loads(json.dumps(m.INITIAL_STATE))
        result, ops, _ = m.add_component({"id": "p", "parent": "root", "type": "PieChart", "props": {}}, state)
        self.assertTrue(result.startswith("error") and not ops)
        result, ops, _ = m.add_component({"id": "x", "parent": "nope", "type": "Text", "props": {"text": "a"}}, state)
        self.assertIn("does not exist", result)

    def test_open_ended_custom_event_and_action(self):
        m = lab("01_ag_ui", "open_ended")
        model = scripted(m.script)
        events = list(m.run(agui.run_input(PROMPT), model))
        custom = [e for e in events if e["type"] == "CUSTOM"]
        self.assertEqual(custom[0]["name"], "voltpilot.generated_html")
        events2 = list(m.run(m.click(PROMPT, events, "schedule_ev_charge", {"window": "10:30-15:00"}), model))
        self.assertEqual(agui.check_sequence(events2), [])
        self.assertEqual(agui.final_state(events2)["ev"]["status"], "scheduled")
        refused = list(m.run(m.click(PROMPT, events, "wipe_disk", {}), model))
        self.assertEqual([e["type"] for e in refused], ["RUN_STARTED", "RUN_ERROR"])

    def test_open_ended_refuses_networked_html(self):
        m = lab("01_ag_ui", "open_ended")
        result, _ops, extra = m.render_html({"title": "x", "html": "<script>fetch('https://x')</script>"}, {})
        self.assertTrue(result.startswith("error") and not extra)

    def test_mixed_round_trip(self):
        m = lab("01_ag_ui", "mixed")
        model = scripted(m.script)
        events = list(m.run(agui.run_input(PROMPT), model))
        tree = catalog.flat_to_tree(agui.final_state(events)["ui"])
        self.assertIn("GeneratedView", {n["type"] for n in catalog.walk(tree)})
        events2 = list(m.run(m.click(PROMPT, events, "schedule_ev_charge", {"window": "10:30-15:00"}), model))
        after = catalog.flat_to_tree(agui.final_state(events + events2)["ui"])
        self.assertEqual(after["children"][1]["props"]["variant"], "success")


if __name__ == "__main__":
    unittest.main()
