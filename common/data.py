"""VoltPilot fixture data: one home, one week, one EV.

Every lab in this repo answers the same question about the same numbers:

    "How did my solar do this week, and when should I charge the EV?"

Keeping the data fixed means the only thing that changes from lab to lab is
*how the interface is produced and delivered* - which is the point of the
assignment. `summary()` derives every number that appears on screen, and
tests/test_common.py checks that the scripted model replies quote exactly
these numbers.
"""

from __future__ import annotations

PROMPT = "How did my solar do this week, and when should I charge the EV?"

# kWh per day. use = (solar - export) + import  (checked in tests)
WEEK = [
    {"day": "Mon", "solar": 16.8, "use": 24.1, "import": 9.0, "export": 1.7},
    {"day": "Tue", "solar": 19.4, "use": 22.8, "import": 6.6, "export": 3.2},
    {"day": "Wed", "solar": 21.2, "use": 23.5, "import": 5.4, "export": 3.1},
    {"day": "Thu", "solar": 14.1, "use": 25.9, "import": 12.3, "export": 0.5},
    {"day": "Fri", "solar": 18.9, "use": 21.7, "import": 5.6, "export": 2.8},
    {"day": "Sat", "solar": 22.6, "use": 19.8, "import": 2.1, "export": 4.9},
    {"day": "Sun", "solar": 20.3, "use": 20.6, "import": 4.9, "export": 4.6},
]
LAST_WEEK_SOLAR = 122.3
IMPORT_RATE = 0.26   # $/kWh, blended
EXPORT_RATE = 0.08   # $/kWh feed-in credit

BATTERY = {"pct": 64, "capacity_kwh": 13.5}

TARIFF = [  # (start hour, end hour, $/kWh, band)
    (0, 6, 0.12, "off-peak"),
    (6, 16, 0.24, "mid"),
    (16, 21, 0.48, "peak"),
    (21, 24, 0.24, "mid"),
]

EV = {"name": "Model Y", "soc": 38, "target": 80, "battery_kwh": 75.0, "charger_kw": 7.2}

# Today, kW averaged per hour (0..23) - the open-ended "energy clock" draws these.
SOLAR_KW = [0, 0, 0, 0, 0, 0, 0.2, 0.9, 1.8, 2.9, 3.8, 4.5, 4.8, 4.6, 4.0, 3.1, 2.0, 1.0, 0.3, 0, 0, 0, 0, 0]
LOAD_KW = [0.4, 0.35, 0.3, 0.3, 0.3, 0.4, 0.9, 1.4, 1.1, 0.8, 0.7, 0.7, 0.9, 0.7, 0.7, 0.9, 1.3, 2.1, 2.6, 2.4, 1.9, 1.4, 0.9, 0.6]

# The three charge windows the copilot compares (cost estimates for 31.5 kWh).
CHARGE_WINDOWS = [
    {"window": "10:30-15:00", "source": "Solar surplus + top-up", "cost": 1.10},
    {"window": "00:00-04:30", "source": "Off-peak grid ($0.12/kWh)", "cost": 3.78},
    {"window": "16:00-20:30", "source": "Peak grid ($0.48/kWh)", "cost": 15.12},
]

# The only actions any surface in this repo may trigger. Servers check this list.
ALLOWED_ACTIONS = {"schedule_ev_charge", "dismiss"}


def rate_at(hour: int) -> float:
    for start, end, rate, _band in TARIFF:
        if start <= hour < end:
            return rate
    raise ValueError(hour)


def summary() -> dict:
    """Every number the dashboards show, derived from the rows above."""
    solar = round(sum(d["solar"] for d in WEEK), 1)
    use = round(sum(d["use"] for d in WEEK), 1)
    imp = round(sum(d["import"] for d in WEEK), 1)
    exp = round(sum(d["export"] for d in WEEK), 1)
    kwh_needed = round(EV["battery_kwh"] * (EV["target"] - EV["soc"]) / 100, 1)
    best = min(CHARGE_WINDOWS, key=lambda w: w["cost"])
    worst = max(CHARGE_WINDOWS, key=lambda w: w["cost"])
    return {
        "solar_kwh": solar,
        "use_kwh": use,
        "import_kwh": imp,
        "export_kwh": exp,
        "self_sufficiency_pct": round(100 * (use - imp) / use),
        "solar_delta_pct": round(100 * (solar - LAST_WEEK_SOLAR) / LAST_WEEK_SOLAR),
        "import_cost": round(imp * IMPORT_RATE, 2),
        "export_credit": round(exp * EXPORT_RATE, 2),
        "best_day": max(WEEK, key=lambda d: d["solar"])["day"],
        "ev_kwh_needed": kwh_needed,
        "ev_hours": round(kwh_needed / EV["charger_kw"], 1),
        "best_window": best["window"],
        "best_cost": best["cost"],
        "saving_vs_peak": round(worst["cost"] - best["cost"], 2),
        "battery_pct": BATTERY["pct"],
    }


def money(x: float) -> str:
    return f"${x:,.2f}"


if __name__ == "__main__":
    import json

    print(json.dumps(summary(), indent=2))
