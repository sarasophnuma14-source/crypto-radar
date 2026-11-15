"""MANIPULATION DETECTOR: riesgo 0-100 de que el movimiento no sea demanda orgánica.

Cada punto de riesgo viene con su evidencia medible (fecha, valor y umbral). El resultado es un RIESGO, no una
acusación: nunca se afirma que hubo manipulación. Las métricas de libro de órdenes (spread, profundidad) solo
existen en vivo; si faltan, se indica "N/D" y no cuentan.
"""
from __future__ import annotations
import datetime as dt
from .features import val, chg, close_location

LEVELS = ((60, "ALTO"), (30, "MEDIO"), (0, "BAJO"))


def _day(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).strftime("%Y-%m-%d")


def evaluate(f, i, market_cap=None, book=None, book_prev=None):
    ev, risk = [], 0.0

    def add(points, text):
        nonlocal risk
        risk += points
        ev.append({"points": points, "text": text})

    avg = val(f.vol_avg20_prev, i)
    # 1. Volumen anormal sin continuidad: pico ≥ 5× y en los 3 días siguientes se apaga y devuelve la subida
    for j in range(max(21, i - 10), i - 2):
        a = val(f.vol_avg20_prev, j)
        if not a or f.v[j] < 5 * a:
            continue
        after = f.v[j + 1:j + 4]
        gain = f.c[j] - f.c[j - 1]
        gave_back = gain > 0 and (f.c[min(i, j + 3)] - f.c[j - 1]) < 0.5 * gain
        if after and max(after) < 1.5 * a and gave_back:
            add(20, f"Pico de volumen {f.v[j] / a:.1f}× el {_day(f.t[j])} sin continuidad: el volumen se apagó y el precio devolvió más de la mitad")
            break
    # 2. Rupturas falsas en 60 días (cierre sobre el máximo de 20 días y vuelta bajo él en ≤ 3 días)
    fails = 0
    for j in range(max(21, i - 60), i - 2):
        res = val(f.hh20_prev, j)
        if res and f.c[j] > res and min(f.c[j + 1:j + 4]) < res:
            fails += 1
    if fails >= 2:
        add(min(25, 10 * fails), f"{fails} rupturas falsas en 60 días (cerró sobre la resistencia y volvió a caer en ≤ 3 días)")
    # 3. Mechas superiores largas en días de mucho volumen (venta agresiva en el pico)
    wicks = 0
    for j in range(max(1, i - 9), i + 1):
        rng = f.h[j] - f.l[j]
        a = val(f.vol_avg20_prev, j)
        if rng > 0 and a and f.v[j] > 2 * a and (f.h[j] - max(f.o[j], f.c[j])) / rng > 0.6:
            wicks += 1
    if wicks:
        add(min(20, 10 * wicks), f"{wicks} vela(s) con mecha superior > 60% del rango y volumen > 2× en 10 días")
    # 4. Movimiento vertical sin liquidez
    for j in range(max(1, i - 9), i + 1):
        r = val(f.ret, j)
        a = val(f.vol_avg20_prev, j)
        if r is not None and r > 0.25 and a is not None and a < 5e6:
            add(20, f"Subida de {r * 100:.0f}% el {_day(f.t[j])} con volumen medio de solo ${a / 1e6:.1f} M/día")
            break
    # 5. Desviación extrema respecto al VWAP de 20 días
    vw = val(f.vwap20, i)
    if vw and f.c[i] > vw * 1.25:
        add(10, f"Precio {(f.c[i] / vw - 1) * 100:.0f}% sobre su VWAP de 20 días")
    # 6. Variaciones extremas repetidas
    extreme = sum(1 for j in range(max(1, i - 29), i + 1) if (val(f.ret, j) is not None and abs(f.ret[j]) > 0.30))
    if extreme >= 2:
        add(min(15, 5 * extreme), f"{extreme} días con variación mayor a ±30% en el último mes")
    # 7. Patrón pump & dump: +60% en ≤ 3 días y −35% desde el pico en ≤ 7 días
    for j in range(max(4, i - 20), i + 1):
        base = min(f.c[j - 3:j])
        if base and f.h[j] / base - 1 >= 0.60:
            after = f.l[j:min(i, j + 7) + 1]
            if after and min(after) <= f.h[j] * 0.65:
                add(25, f"Patrón de bombeo y descarga: +{(f.h[j] / base - 1) * 100:.0f}% hasta el {_day(f.t[j])} y caída posterior de más de 35%")
                break
    # 8. Token pequeño con rotación desproporcionada
    if market_cap:
        turnover = (avg or 0) / market_cap
        if market_cap < 50e6 and turnover > 0.5:
            add(15, f"Capitalización de ${market_cap / 1e6:.0f} M con rotación diaria de {turnover * 100:.0f}% del valor")
        elif turnover > 1.0:
            add(10, f"Volumen diario mayor que la capitalización ({turnover * 100:.0f}%)")
    # 9. Libro de órdenes (solo en vivo)
    book_note = "N/D (sin libro de órdenes en este análisis)"
    if book:
        book_note = None
        sp = book.get("spread_pct")
        if sp is not None and sp > 0.5:
            add(10, f"Spread anormal de {sp:.2f}%")
        d, d0 = book.get("depth_usd_2pct"), (book_prev or {}).get("depth_usd_2pct")
        if d and d0 and d < d0 * 0.4:
            add(10, f"La profundidad del libro (±2%) cayó {(1 - d / d0) * 100:.0f}% desde la lectura anterior")
    risk = min(100.0, risk)
    level = next(name for th, name in LEVELS if risk >= th)
    return {"risk": round(risk), "level": level, "evidence": ev, "book": book_note,
            "note": "Riesgo estimado con datos públicos; no prueba que haya manipulación."}
