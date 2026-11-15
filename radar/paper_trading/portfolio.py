"""Vista de la cartera simulada a partir del estado del motor (posiciones, exposición, riesgo abierto)."""


def snapshot(state, marks=None):
    marks = marks or state.get("last_px", {})
    rows = []
    for sym, p in state.get("pos", {}).items():
        px = marks.get(sym, p["entry_open"])
        rows.append({"symbol": sym, "entry_date": p["entry_date"], "qty": p["qty"], "entry_px": p["entry"],
                     "mark": px, "stale_days": state.get("missing", {}).get(sym, 0), "value_usd": p["qty"] * px,
                     "stop": p["stop"], "unrealized_usd": p["qty"] * px - p["cost"],
                     "open_risk_usd": p["qty"] * max(0.0, px - p["stop"]), "limit_at_entry": p.get("limit")})
    eq = state["cash"] + sum(r["value_usd"] for r in rows)
    return {"cash": state["cash"], "equity": eq, "positions": rows,
            "exposure_pct": (eq - state["cash"]) / eq * 100 if eq > 0 else 0.0,
            "open_risk_pct": sum(r["open_risk_usd"] for r in rows) / eq * 100 if eq > 0 else 0.0,
            "pending_orders": state.get("pend_in", []), "pending_exits": state.get("pend_out", {})}
