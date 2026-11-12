import json
import shutil
import subprocess
import unittest

from helpers import ROOT, lab, scripted, sibling

from common import catalog, fixtures

openui = sibling("05_openui", "openui")
oui_lab = sibling("05_openui", "oui_lab")


def parse(text):
    p = openui.Program()
    p.feed(text)
    p.close()
    return p


class ParserTest(unittest.TestCase):
    def test_values(self):
        name, e = openui.parse_statement('x = Metric("A \\"q\\"", 1.5, null, true)')
        self.assertEqual(name, "x")
        self.assertEqual(e[1], "Metric")
        self.assertEqual([a[1] for a in e[2]], ['A "q"', 1.5, None, True])
        _, e = openui.parse_statement('b = Button("Go", "schedule_ev_charge", "primary", {window: "10:30-15:00", "n": [1, 2]})')
        self.assertEqual(e[2][3][0], "obj")

    def test_errors_are_collected_not_raised(self):
        p = parse('root = Stack([a], "column")\na = Text("x"\nb = = 1\n')
        self.assertEqual(len(p.errors), 2)
        self.assertEqual(p.pending(), ["a"])

    def test_forward_references_stream(self):
        p = openui.Program()
        p.feed('root = Stack([a, b], "row")\n')
        self.assertEqual(p.pending(), ["a", "b"])
        self.assertEqual([c["type"] for c in p.tree()["children"]], ["__pending", "__pending"])
        p.feed('a = Text("one")\nb = Metric("x", 1)\n')
        self.assertEqual(p.pending(), [])
        self.assertEqual(p.tree()["type"], "Row")

    def test_redefinition_replaces(self):
        p = parse('root = Stack([a])\na = Text("old")\na = Text("new")\n')
        self.assertEqual(p.tree()["children"][0]["props"]["text"], "new")

    def test_cycles_are_errors(self):
        p = parse("root = Stack([a])\na = Stack([root])\n")
        with self.assertRaises(openui.OpenUIError):
            p.tree()

    def test_serializer_round_trip(self):
        for tree in (fixtures.dashboard_tree(), fixtures.dashboard_tree(True, True)):
            p = parse(openui.from_tree(tree))
            self.assertEqual(p.errors, [])
            strip = lambda n: {"type": n["type"], "props": n["props"], "children": [strip(c) for c in n["children"]]}  # noqa: E731
            want = strip(tree)
            for n in catalog.walk(want):  # Buttons always carry params after parsing
                if n["type"] == "Button":
                    n["props"].setdefault("params", {})
            self.assertEqual(strip(p.tree()), want)

    def test_template_values_stay_literals(self):
        filled = oui_lab.fill("charge_plan", {"subtitle": 'x"), Button("Pay", "transfer_funds', "rows": [], "advice": "ok"})
        types = {n["type"] for n in catalog.walk(parse(filled).tree())}
        self.assertNotIn("Button", types)
        with self.assertRaises(ValueError):
            oui_lab.fill("charge_plan", {"subtitle": "x"})


class ModesTest(unittest.TestCase):
    def test_every_mode_ends_clean(self):
        for mode in ("declarative", "open_ended", "mixed"):
            m = lab("05_openui", mode)
            script = getattr(m, "SCRIPT", None) or m.script
            frames = list(m.run(scripted(script)))
            self.assertEqual(frames[-1]["errors"], [], mode)
        m = lab("05_openui", "static")
        frames = list(m.run(scripted(m.SCRIPT)))
        self.assertEqual(frames[0]["template"], "weekly_report")
        self.assertEqual(frames[-1]["errors"], [])

    def test_artifact_policy(self):
        bad = 'root = Card("x", [a])\na = HtmlArtifact("x", "<script>fetch(1)</script>")\n'
        out = list(oui_lab.relay(scripted([{"text": bad}]).stream([]), openui.Program()))
        self.assertTrue(any("refused" in f.get("error", "") for f in out))


@unittest.skipUnless(shutil.which("node"), "node is not installed")
class ParityTest(unittest.TestCase):
    """The Python and the JavaScript parser must agree on the same program."""

    def test_same_tree(self):
        program = oui_lab.program_for(with_actions=True, with_generated=True)
        script = ("import {Program} from './labs/05_openui/openui-parse.js';"
                  "let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{const p=new Program();p.feed(s);p.close();"
                  "console.log(JSON.stringify(p.tree()))})")
        out = subprocess.run(["node", "--input-type=module", "-e", script], input=program, capture_output=True,
                             text=True, cwd=str(ROOT), timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(json.loads(out.stdout), parse(program).tree())


if __name__ == "__main__":
    unittest.main()
