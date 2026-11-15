"""SMART PORTFOLIO: tamaño de posición y límites de riesgo (spot, sin apalancamiento).

Lo usan igual el backtest y el panel en vivo, así que los límites que se prueban son los que se aplican.
"""
from __future__ import annotations
import math

DEFAULT_LIMITS = {
    "risk_per_trade_pct": 1.0,      # % del capital que se pierde si salta el stop
    "max_position_pct": 20.0,       # % máximo del capital en un activo
    "max_category_pct": 40.0,       # % máximo en una misma categoría (memecoins, IA, L1...)
    "max_positions": 6,
    "max_open_risk_pct": 5.0,       # suma del riesgo hasta el stop de todas las posiciones abiertas
    "max_correlation": 0.85,        # correlación máxima (60 días) con una posición ya abierta
    "max_adv_pct": 1.0,             # la posición no puede superar este % del volumen diario medio (liquidez)
    "dd_reduce_pct": 10.0,          # drawdown desde el máximo que reduce el tamaño a la mitad
    "dd_stop_pct": 20.0,            # drawdown desde el máximo que bloquea entradas nuevas
    "min_order_usd": 10.0,
}


def correlation(f_a, ia, f_b, ib, w=60):
    ra = [f_a.ret[j] for j in range(ia - w + 1, ia + 1) if j > 0]
    rb = [f_b.ret[j] for j in range(ib - w + 1, ib + 1) if j > 0]
    n = min(len(ra), len(rb))
    if n < 20:
        return None
    ra, rb = ra[-n:], rb[-n:]
    if None in ra or None in rb:
        return None
    ma, mb = sum(ra) / n, sum(rb) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(ra, rb))
    va = math.sqrt(sum((x - ma) ** 2 for x in ra)); vb = math.sqrt(sum((y - mb) ** 2 for y in rb))
    return cov / (va * vb) if va and vb else None


def size(equity, peak_equity, cash, entry, stop, positions, limits=None, regime_mult=1.0, category=None,
         avg_volume_usd=None, max_alt_exposure_pct=None, is_alt=True, corr_with=None):
    """positions: [{"value", "risk_usd", "category", "is_alt"}]. corr_with: lista de correlaciones con las abiertas.
    Devuelve {"qty", "value", "risk_usd", "ok", "reasons"} con el motivo de cada recorte o rechazo."""
    L = dict(DEFAULT_LIMITS); L.update(limits or {})
    reasons = []
    if entry <= 0 or stop <= 0 or stop >= entry:
        return {"qty": 0, "value": 0, "risk_usd": 0, "ok": False, "reasons": ["Stop inválido"]}
    dd = (1 - equity / peak_equity) * 100 if peak_equity else 0
    if dd >= L["dd_stop_pct"]:
        return {"qty": 0, "value": 0, "risk_usd": 0, "ok": False,
                "reasons": [f"Protección por drawdown: {dd:.1f}% ≥ {L['dd_stop_pct']}% (sin entradas nuevas)"]}
    if len(positions) >= L["max_positions"]:
        return {"qty": 0, "value": 0, "risk_usd": 0, "ok": False, "reasons": [f"Máximo de {L['max_positions']} posiciones"]}
    if corr_with:
        hi = max(c for c in corr_with if c is not None) if any(c is not None for c in corr_with) else None
        if hi is not None and hi > L["max_correlation"]:
            return {"qty": 0, "value": 0, "risk_usd": 0, "ok": False,
                    "reasons": [f"Correlación {hi:.2f} con una posición abierta (> {L['max_correlation']})"]}
    mult = regime_mult
    if dd >= L["dd_reduce_pct"]:
        mult *= 0.5; reasons.append(f"Tamaño a la mitad por drawdown de {dd:.1f}%")
    risk_usd = equity * L["risk_per_trade_pct"] / 100 * mult
    per_unit = entry - stop
    value = risk_usd / per_unit * entry
    caps = [("máximo por activo", equity * L["max_position_pct"] / 100)]
    open_risk = sum(p.get("risk_usd", 0) for p in positions)
    room_risk = equity * L["max_open_risk_pct"] / 100 - open_risk
    caps.append(("riesgo abierto total", max(0.0, room_risk) / per_unit * entry))
    if category:
        used = sum(p["value"] for p in positions if p.get("category") == category)
        caps.append((f"categoría {category}", max(0.0, equity * L["max_category_pct"] / 100 - used)))
    if is_alt and max_alt_exposure_pct is not None:
        used = sum(p["value"] for p in positions if p.get("is_alt", True))
        caps.append(("exposición a altcoins del régimen", max(0.0, equity * max_alt_exposure_pct / 100 - used)))
    if avg_volume_usd:
        caps.append(("liquidez (volumen diario)", avg_volume_usd * L["max_adv_pct"] / 100))
    caps.append(("caja disponible", cash))
    for name, cap in caps:
        if value > cap:
            value = cap; reasons.append(f"Recortado por {name}")
    if value < L["min_order_usd"]:
        return {"qty": 0, "value": 0, "risk_usd": 0, "ok": False, "reasons": reasons + ["Tamaño resultante menor al mínimo"]}
    qty = value / entry
    return {"qty": qty, "value": value, "risk_usd": qty * per_unit, "ok": True, "reasons": reasons}
