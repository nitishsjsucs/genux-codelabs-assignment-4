import unittest

from helpers import lab, scripted, sibling

from common import catalog

a2ui = sibling("02_a2ui", "a2ui")
surf = sibling("02_a2ui", "a2ui_surfaces")


def frames_to_client(frames):
    client = a2ui.Client()
    for f in frames:
        if "a2ui" in f:
            client.apply(f["a2ui"])
    return client


class EnvelopeTest(unittest.TestCase):
    def test_builders_validate(self):
        self.assertEqual(a2ui.validate(a2ui.create_surface("s", a2ui.BASIC_CATALOG)), [])
        self.assertEqual(a2ui.validate(a2ui.update_data_model("s", "/a", 1)), [])
        self.assertEqual(a2ui.validate(a2ui.delete_surface("s")), [])

    def test_bad_messages(self):
        self.assertIn("exactly one", a2ui.validate({"version": a2ui.VERSION, "createSurface": {}, "deleteSurface": {}})[0])
        self.assertTrue(a2ui.validate({"version": "v0.8", "deleteSurface": {"surfaceId": "s"}}))
        errs = a2ui.validate(a2ui.update_components("s", [{"id": "b", "component": "Button", "child": "t"}]), a2ui.BASIC_CATALOG)
        self.assertTrue(any("missing 'action'" in e for e in errs))
        errs = a2ui.validate(a2ui.update_components("s", [{"id": "t", "component": "Text", "text": "x", "colour": "red"}]), a2ui.BASIC_CATALOG)
        self.assertTrue(any("unknown property 'colour'" in e for e in errs))

    def test_custom_catalog_is_the_only_way_to_html(self):
        client = a2ui.Client()
        client.apply(a2ui.create_surface("s", a2ui.BASIC_CATALOG))
        frame = [{"id": "root", "component": "HtmlFrame", "title": "x", "html": "<b>x</b>"}]
        self.assertTrue(client.apply(a2ui.update_components("s", frame)))
        client.apply(a2ui.create_surface("o", a2ui.ENERGY_OPEN_CATALOG))
        self.assertEqual(client.apply(a2ui.update_components("o", frame)), [])

    def test_bindings_resolve(self):
        client = a2ui.Client()
        client.apply(a2ui.create_surface("s", a2ui.ENERGY_CATALOG))
        client.apply(a2ui.update_components("s", [{"id": "root", "component": "Metric", "label": "Solar", "value": {"path": "/x/v"}}]))
        client.apply(a2ui.update_data_model("s", "/x", {"v": "1 kWh"}))
        self.assertEqual(client.to_tree("s")["props"]["value"], "1 kWh")

    def test_streamed_jsonl_lines(self):
        model = scripted([{"text": a2ui.to_jsonl([a2ui.delete_surface("s")]) + "not json\n"}])
        out = list(a2ui.jsonl_messages(model.stream([])))
        self.assertIn("deleteSurface", out[0])
        self.assertIn("error", out[1])


class ModesTest(unittest.TestCase):
    def test_static_model_may_only_send_data(self):
        m = lab("02_a2ui", "static")
        frames = list(m.run(scripted(m.SCRIPT), a2ui.Client()))
        self.assertEqual([f["from"] for f in frames[:2]], ["app", "app"])
        self.assertTrue(all("updateDataModel" in f["a2ui"] for f in frames[2:]))
        client = a2ui.Client()
        for msg in m.APP_MESSAGES:
            client.apply(msg)
        forged = scripted([{"text": a2ui.to_jsonl([a2ui.update_components(surf.SID, [{"id": "x", "component": "Text", "text": "y"}])])}])
        out = list(surf.relay(forged.stream([]), client, allowed={"updateDataModel"}))
        self.assertIn("refused", out[0]["error"])

    def test_declarative_surface_is_complete(self):
        m = lab("02_a2ui", "declarative")
        client = frames_to_client(m.run(scripted(m.SCRIPT), a2ui.Client()))
        self.assertEqual(client.missing_refs(surf.SID), [])
        self.assertEqual(catalog.validate_tree(client.to_tree(surf.SID), allow_generated=False), [])

    def test_mixed_action_reply(self):
        m = lab("02_a2ui", "mixed")
        model = scripted(m.script)
        page = frames_to_client(m.run(model, a2ui.Client()))
        msg = a2ui.action_message("schedule_ev_charge", surf.SID, "btn-schedule", {"window": "10:30-15:00"})
        reply = list(m.on_action(msg, model))
        for f in reply:
            self.assertEqual(page.apply(f["a2ui"]), [])
        self.assertIn("booked", page.surfaces[surf.SID].components["root"]["children"])
        self.assertTrue(page.surfaces[surf.SID].data["ev"]["status"].startswith("Booked"))
        refused = list(m.on_action(a2ui.action_message("pay", surf.SID, "x", {}), model))
        self.assertIn("refused", refused[0]["error"])

    def test_open_ended_policy(self):
        m = lab("02_a2ui", "open_ended")
        bad = [{"from": "model", "a2ui": a2ui.update_data_model(surf.SID, "/clock/html", "<script>new WebSocket('x')</script>")}]
        self.assertIn("refused", list(m.checked(iter(bad)))[0]["error"])


if __name__ == "__main__":
    unittest.main()
