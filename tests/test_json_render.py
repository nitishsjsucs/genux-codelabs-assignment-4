import unittest

from helpers import lab, scripted, sibling

from common import catalog

jr = sibling("04_json_render", "jsonrender")
jr_lab = sibling("04_json_render", "jr_lab")


def build(frames):
    stream = jr.SpecStream()
    for f in frames:
        if "patch" in f:
            stream.push(f["patch"])
    return stream.spec


class SpecTest(unittest.TestCase):
    def test_expressions(self):
        state = {"a": {"b": 2}, "n": "x"}
        self.assertEqual(jr.resolve_value({"$state": "/a/b"}, state), 2)
        self.assertEqual(jr.resolve_value({"$template": "${/n}-${/a/b}-${/missing}"}, state), "x-2-")
        self.assertEqual(jr.resolve_value([{"$state": "/n"}, 1], state), ["x", 1])

    def test_button_events_and_custom_html(self):
        spec = {"root": "r", "state": {"w": "10:30-15:00", "h": "<b>x</b>"}, "elements": {
            "r": {"type": "Column", "props": {}, "children": ["b", "c"]},
            "b": {"type": "Button", "props": {"label": "Go"}, "on": {"press": {"action": "schedule_ev_charge", "params": {"window": {"$state": "/w"}}}}},
            "c": {"type": "CustomHtml", "props": {"title": "c", "html": {"$state": "/h"}}}}}
        tree = jr.to_canonical(spec)
        self.assertEqual(tree["children"][0]["props"]["params"], {"window": "10:30-15:00"})
        self.assertEqual(tree["children"][1]["type"], "GeneratedView")
        self.assertEqual(jr.validate(spec, allow_custom=True), [])
        self.assertTrue(jr.validate(spec, allow_custom=False))

    def test_patch_stream_round_trip(self):
        spec = jr_lab.dashboard_spec(True, True)
        patches = jr.spec_to_patches(spec)
        self.assertEqual(patches[0], {"op": "add", "path": "/root", "value": "main"})
        stream = jr.SpecStream()
        for p in patches:
            self.assertIsNone(stream.push(p))
        self.assertEqual(stream.spec, spec)

    def test_partial_specs_render(self):
        spec = jr_lab.dashboard_spec()
        stream = jr.SpecStream()
        for p in jr.spec_to_patches(spec)[:4]:
            stream.push(p)
        self.assertEqual(jr.to_canonical(stream.spec)["type"], "Column")  # half a spec still draws

    def test_writable_gate(self):
        stream = jr.SpecStream({"root": "r", "elements": {}, "state": {"x": 1}}, writable=["/state"])
        self.assertIsNone(stream.push({"op": "replace", "path": "/state/x", "value": 2}))
        self.assertIn("refused", stream.push({"op": "add", "path": "/elements/y", "value": {}}))
        self.assertIn("refused", stream.push({"op": "replace", "path": "/root", "value": "y"}))


class ModesTest(unittest.TestCase):
    def test_static(self):
        m = lab("04_json_render", "static")
        frames = list(m.run(scripted(m.SCRIPT)))
        self.assertIn("spec", frames[0])
        self.assertEqual(len([f for f in frames if "patch" in f]), 8)

    def test_declarative_and_mixed_validate(self):
        for mode, custom in (("declarative", False), ("mixed", True), ("open_ended", True)):
            m = lab("04_json_render", mode)
            frames = list(m.run(scripted(m.SCRIPT)))
            self.assertEqual(frames[-1]["errors"], [], mode)
            self.assertEqual(jr.validate(build(frames), allow_custom=custom), [], mode)

    def test_mixed_action(self):
        m = lab("04_json_render", "mixed")
        frames = list(m.run(scripted(m.SCRIPT)))
        stream = jr.SpecStream(build(frames))
        for f in jr_lab.handle_action({"action": "schedule_ev_charge", "params": {"window": "10:30-15:00"}}, scripted(m.SCRIPT), m.SYSTEM, m.SPEC):
            self.assertIsNone(stream.push(f["patch"]))
        tree = jr.to_canonical(stream.spec)
        self.assertEqual(tree["children"][1]["props"]["variant"], "success")
        self.assertEqual(catalog.validate_tree(tree), [])

    def test_policy_on_custom_html(self):
        evil = scripted([{"text": jr.to_jsonl([{"op": "add", "path": "/state/clock", "value": {"html": "<form action='/x'>"}}])}])
        out = list(jr_lab.relay(evil.stream([]), jr.SpecStream()))
        self.assertIn("refused", out[0]["error"])


if __name__ == "__main__":
    unittest.main()
