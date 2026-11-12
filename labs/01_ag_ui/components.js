// Mode 1 (static): the frontend's own components. The agent may only pick one
// by calling the tool with the same name and supply typed props; the layout of
// each component is decided here, by the developer, not by the model.
// They are built from catalog nodes so they share the look of every other lab.

const money = (x) => `$${Number(x).toFixed(2)}`;
const n = (type, props, children = []) => ({ type, props, children });

export const FRONTEND_COMPONENTS = {
  show_energy_summary: (a) =>
    n("Row", { gap: "medium" }, [
      n("Metric", { label: "Solar generated", value: `${a.solar_kwh} kWh`, delta: `+${a.solar_delta_pct}% vs last week`, tone: "good" }),
      n("Metric", { label: "Self-sufficiency", value: `${a.self_sufficiency_pct}%` }),
      n("Metric", { label: "Grid import cost", value: money(a.import_cost), tone: "bad" }),
      n("Metric", { label: "Home battery", value: `${a.battery_pct}%` }),
    ]),
  show_solar_chart: (a) =>
    n("Card", { title: "Solar vs usage" }, [n("BarChart", { title: "Solar generated per day", labels: a.days, values: a.solar_kwh, unit: "kWh" })]),
  show_charge_plan: (a) =>
    n("Card", { title: "When to charge the EV" }, [
      n("Table", { columns: ["Window", "Source", "Est. cost"], rows: a.windows.map((w) => [w.window, w.source, money(w.cost)]) }),
      n("Text", { text: a.recommendation }),
    ]),
};
