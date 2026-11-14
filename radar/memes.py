"""Estrategia de memecoins validada con backtest (2021–2024 diseño, 2025→hoy prueba a ciegas).

Regla:
  1. Señal al cierre diario (00:00 UTC): volumen del día ≥ 5 × su promedio de 20 días
     Y cierre > máximo de los 20 días anteriores
     Y la vela NO subió más de +30 % ese día (no perseguir el techo del pump).
  2. Compra a la apertura del día siguiente.
  3. Salida: lo primero que ocurra → objetivo +60 %, stop −15 % o 5 días.
  4. Tamaño: 10 % del capital por operación, máximo 8 abiertas.

La app NO compra nada: avisa por Telegram y lleva un seguimiento en modo práctica (papel)
para medir el acierto real en vivo. Solo análisis, no asesoría financiera.
"""
from __future__ import annotations

import datetime as dt
import time
import traceback

from . import alerts, data, storage
from .config import load_settings

MEMES = ["DOGE", "SHIB", "PEPE", "FLOKI", "BONK", "WIF", "BOME", "MEME", "1000SATS", "1000CAT", "1000CHEEMS",
         "1MBABYDOGE", "NEIRO", "TURBO", "PEOPLE", "PNUT", "ACT", "TRUMP", "PENGU", "DOGS", "BROCCOLI714",
         "MUBARAK", "币安人生", "TST", "GIGGLE", "BANANAS31"]

RULE = {"vol_mult": 5.0, "lookback": 20, "max_day_gain": 0.30, "take_profit": 0.60, "stop_loss": 0.15,
        "max_days": 5, "size_pct": 10.0, "max_open": 8, "min_avg_volume_usd": 2_000_000}

BACKTEST = {"periodo": "2025-01-01 → 2026-11-13 (prueba a ciegas)", "acierto_pct": 44.9, "retorno_pct": 31.3,
            "max_dd_pct": -12.3, "profit_factor": 1.89, "operaciones": 49}

status = {"last_check": None, "last_error": None, "checking": False}
FILE = "memes.json"


def _now():
    return dt.datetime.now(dt.timezone.utc)


def _day(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def _load():
    st = storage.read(FILE, None) or {}
    st.setdefault("signals", []); st.setdefault("trades", [])
    return st


def evaluate(k, rule=RULE):
    """k: velas diarias (t,o,h,l,c,v) donde la ÚLTIMA puede ser la de hoy (abierta).
    Devuelve dict con la señal de la última vela CERRADA, o None."""
    today = _now().strftime("%Y-%m-%d")
    n = len(k["c"])
    last = n - 1
    if n and _day(k["t"][-1]) == today:
        last = n - 2                        # la vela de hoy aún no cerró
    lb = rule["lookback"]
    if last < lb + 5:
        return None
    v, c, h = k["v"], k["c"], k["h"]
    prev_v = v[last - lb:last]
    vavg = sum(prev_v) / len(prev_v)
    hh = max(h[last - lb:last])
    avg30 = sum(v[max(0, last - 29):last + 1]) / len(v[max(0, last - 29):last + 1])
    day_gain = c[last] / c[last - 1] - 1 if c[last - 1] else 0
    ok = (vavg > 0 and v[last] >= rule["vol_mult"] * vavg and c[last] > hh
          and day_gain <= rule["max_day_gain"] and avg30 >= rule["min_avg_volume_usd"])
    if not ok:
        return None
    entry = k["o"][last + 1] if last + 1 < n else c[last]
    return {"signal_day": _day(k["t"][last]), "close": c[last], "vol_x": round(v[last] / vavg, 1),
            "breakout_level": hh, "day_gain_pct": round(day_gain * 100, 1), "entry": entry,
            "entry_known": last + 1 < n}


def check_signals(settings=None):
    settings = settings or load_settings()
    st = _load()
    seen = {(s["symbol"], s["signal_day"]) for s in st["signals"]}
    open_tr = [t for t in st["trades"] if t["status"] == "OPEN"]
    cap = float(settings.get("capital_usd") or 1000)
    new, errors = [], []
    for sym in settings.get("meme_list") or MEMES:
        try:
            k = data.klines(sym + settings.get("quote", "USDT"), "1d", 40)
        except Exception as e:
            errors.append(f"{sym}: {e}")
            continue
        sig = evaluate(k)
        if not sig or (sym, sig["signal_day"]) in seen:
            continue
        e = sig["entry"]
        sig.update({"symbol": sym, "at": _now().isoformat(), "stop": e * (1 - RULE["stop_loss"]),
                    "target": e * (1 + RULE["take_profit"]),
                    "expires": (dt.datetime.fromisoformat(sig["signal_day"]).replace(tzinfo=dt.timezone.utc)
                                + dt.timedelta(days=1 + RULE["max_days"])).isoformat()})
        taken = len(open_tr) < RULE["max_open"] and not any(t["symbol"] == sym for t in open_tr)
        sig["paper"] = taken
        st["signals"].append(sig); new.append(sig)
        if taken:
            usd = cap * RULE["size_pct"] / 100
            tr = {"symbol": sym, "signal_day": sig["signal_day"], "opened": _now().isoformat(), "entry": e,
                  "stop": sig["stop"], "target": sig["target"], "expires": sig["expires"], "usd": usd,
                  "qty": usd / e if e else 0, "status": "OPEN", "last": e}
            st["trades"].append(tr); open_tr.append(tr)
        live = ""
        try:
            px = data.ticker_prices(settings.get("quote", "USDT")).get(sym)
            if px and e and px > e * 1.10:
                live = f"\n⚠️ El precio ya está {((px / e - 1) * 100):.0f}% sobre la entrada: no perseguir."
        except Exception:
            pass
        msg = (f"Ruptura con volumen {sig['vol_x']}× (cierre {sig['signal_day']}).\n"
               f"Entrada: {e:.8g} · Stop −15%: {sig['stop']:.8g} · Objetivo +60%: {sig['target']:.8g}\n"
               f"Salir a más tardar en 5 días. Tamaño sugerido: 10% del capital "
               f"(≈ ${cap * RULE['size_pct'] / 100:,.0f}).{live}"
               + ("" if taken else "\n(Sin cupo en modo práctica: ya hay 8 abiertas.)"))
        alerts.emit(settings, "MEME BREAKOUT", sym, msg, sig, dedupe_hours=20)
    st["signals"] = st["signals"][-300:]
    storage.write(FILE, st)
    return new, errors


def update_trades(settings=None):
    """Recorre velas de 1 hora desde la entrada: stop primero (peor caso), luego objetivo, luego tiempo."""
    settings = settings or load_settings()
    st = _load()
    changed = False
    for t in st["trades"]:
        if t["status"] != "OPEN":
            continue
        try:
            start = int(dt.datetime.fromisoformat(t["signal_day"]).replace(tzinfo=dt.timezone.utc).timestamp() * 1000) + 86_400_000
            rows = data.kline_rows(t["symbol"] + settings.get("quote", "USDT"), "1h", 200, start)
        except Exception:
            continue
        exit_px = why = None
        for r in rows:
            hi, lo = float(r[2]), float(r[3])
            if lo <= t["stop"]:
                exit_px, why = t["stop"], "STOP"; break
            if hi >= t["target"]:
                exit_px, why = t["target"], "OBJETIVO"; break
        if rows:
            t["last"] = float(rows[-1][4])
        if exit_px is None and _now() >= dt.datetime.fromisoformat(t["expires"]):
            exit_px, why = t["last"], "TIEMPO"
        if exit_px is not None:
            fee = 0.001
            t.update({"status": "CLOSED", "exit": exit_px, "reason": why, "closed": _now().isoformat(),
                      "pnl_pct": round(((exit_px * (1 - fee)) / (t["entry"] * (1 + fee)) - 1) * 100, 2)})
            kind = {"STOP": "MEME STOP", "OBJETIVO": "MEME TARGET", "TIEMPO": "MEME TIME EXIT"}[why]
            alerts.emit(settings, kind, t["symbol"],
                        f"Salida por {why.lower()} a {exit_px:.8g} ({t['pnl_pct']:+.1f}%). Operación de práctica cerrada.",
                        {"pnl_pct": t["pnl_pct"]}, dedupe_hours=1)
        changed = True
        time.sleep(0.1)
    if changed:
        storage.write(FILE, st)


def stats(st=None):
    st = st or _load()
    closed = [t for t in st["trades"] if t["status"] == "CLOSED"]
    wins = [t["pnl_pct"] for t in closed if t["pnl_pct"] > 0]
    losses = [-t["pnl_pct"] for t in closed if t["pnl_pct"] <= 0]
    return {"signals": len(st["signals"]), "open": sum(t["status"] == "OPEN" for t in st["trades"]),
            "closed": len(closed), "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else None,
            "profit_factor": round(sum(wins) / sum(losses), 2) if losses and sum(losses) > 0 else None,  # sin pérdidas aún: N/D
            "avg_pnl_pct": round(sum(t["pnl_pct"] for t in closed) / len(closed), 2) if closed else None,
            # cada operación usa 10 % del capital
            "portfolio_pct": round(sum(t["pnl_pct"] for t in closed) * RULE["size_pct"] / 100, 2)}


def run(settings=None):
    if status["checking"]:
        return
    status["checking"] = True
    try:
        settings = settings or load_settings()
        _, errors = check_signals(settings)
        update_trades(settings)
        status["last_check"] = _now().isoformat()
        status["last_error"] = (f"{len(errors)} monedas sin datos: " + "; ".join(errors[:3])) if errors else None
    except Exception as e:
        status["last_error"] = str(e)
        traceback.print_exc()
    finally:
        status["checking"] = False


def state():
    st = _load()
    # El panel no expone la regla, el backtest ni la lista de monedas vigiladas:
    # solo resultados (señal, niveles y desenlace), para que la estrategia no se pueda copiar.
    hidden = {"vol_x", "day_gain_pct"}
    signals = [{k: v for k, v in s.items() if k not in hidden} for s in reversed(st["signals"][-60:])]
    return {"status": status, "stats": stats(st), "signals": signals,
            "open": [t for t in st["trades"] if t["status"] == "OPEN"],
            "closed": list(reversed([t for t in st["trades"] if t["status"] == "CLOSED"]))[:200]}
