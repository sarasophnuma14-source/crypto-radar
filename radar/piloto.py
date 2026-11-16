"""Instrumentación y métricas del piloto cerrado (docs/PLAN_PILOTO_90_DIAS.md §1 y §3).

APAGADA por defecto. Se enciende con CRYPTO_RADAR_PILOT_METRICS=1 y, para las encuestas, además
CRYPTO_RADAR_PILOT_SURVEYS=1. No debe encenderse hasta que G-16 (política de privacidad que mencione este registro)
esté completo, revisado y autorizado por el propietario.

Reglas que cumple el código:
- Solo usuarios autenticados y no administradores.
- «visit», «export_csv» y «tab:<vista>»: como máximo UNA fila por usuario, evento y día UTC. El id de la fila es un
  hash de (usuario, evento, día), así que dos instancias o dos peticiones simultáneas no pueden duplicarla
  (INSERT … ON CONFLICT DO NOTHING). Además hay una caché en memoria para no escribir en la base en cada petición.
- No guarda IP ni contenido: detail = NULL, ip = NULL.
- Sin herramientas externas: todo vive en la tabla activity de la propia base.
- Fechas en UTC (epoch); la interfaz las presenta en la zona local del navegador.

Las métricas se calculan por cohorte semanal (semana ISO del primer inicio de sesión) y cada tasa se publica con
numerador, denominador, intervalo de Wilson al 95 % y los casos pendientes o sin datos.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
import threading
import time

from . import db

DAY = 86400
TABS = ("dash", "early", "market", "breakouts", "memes", "exits", "portfolio", "backtest", "perf", "alerts", "settings")
DAILY = ("visit", "export_csv") + tuple("tab:" + t for t in TABS)
MIN_ACTIVATED = 30                 # por debajo, la decisión es extender el piloto (DECISION_COMERCIAL_GO_NO_GO.md §2)
_seen = set()
_seen_day = {"d": None}
_lock = threading.Lock()


def enabled():
    return os.environ.get("CRYPTO_RADAR_PILOT_METRICS", "").strip() == "1"


def surveys_enabled():
    return enabled() and os.environ.get("CRYPTO_RADAR_PILOT_SURVEYS", "").strip() == "1"


def _day(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).date()


# ------------------------------------------------------------------------------------------------ registro
def record_daily(user, event, now=None):
    """Registra un evento diario. Devuelve True si escribió una fila nueva (o lo intentó), False si no correspondía."""
    if not enabled() or not user or user.get("is_admin") or event not in DAILY:
        return False
    now = now or time.time()
    d = _day(now).isoformat()
    key = (user["id"], event, d)
    with _lock:
        if _seen_day["d"] != d:                       # la caché solo guarda el día en curso
            _seen.clear()
            _seen_day["d"] = d
        if key in _seen:
            return False
        _seen.add(key)
    rid = hashlib.sha256("|".join(key).encode()).hexdigest()[:32]
    q = ("INSERT INTO activity(id, user_id, at, action, detail, ip) VALUES (?, ?, ?, ?, NULL, NULL) "
         + ("ON CONFLICT (id) DO NOTHING" if db.IS_PG else ""))
    if not db.IS_PG:
        q = q.replace("INSERT INTO", "INSERT OR IGNORE INTO")
    try:
        db.execute(q, (rid, user["id"], now, event))
    except Exception:
        with _lock:
            _seen.discard(key)                        # se reintenta en la próxima petición
        return False
    return True


def record_client_event(user, body):
    """Eventos que solo ve el navegador (la exportación CSV se genera en el cliente; el cambio de pestaña también)."""
    ev = str((body or {}).get("event") or "")
    if ev == "tab":
        tab = str((body or {}).get("tab") or "")
        if tab not in TABS:
            return False
        ev = "tab:" + tab
    return record_daily(user, ev)


def reset_cache():
    with _lock:
        _seen.clear()
        _seen_day["d"] = None


# ------------------------------------------------------------------------------------------------ estadística
def wilson(k, n, z=1.96):
    """Intervalo de Wilson al 95 % para una proporción k/n. Con n = 0 no hay intervalo."""
    if not n:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return [round(max(0.0, c - h), 4), round(min(1.0, c + h), 4)]


def rate(k, n, pending=0, missing=0):
    return {"numerador": k, "denominador": n, "tasa": round(k / n, 4) if n else None, "ic95": wilson(k, n),
            "muestra": n, "pendientes": pending, "sin_datos": missing}


# ------------------------------------------------------------------------------------------------ activación
def activation(events, first_login):
    """Momento de activación según PLAN_PILOTO_90_DIAS.md §3, o None.

    Activado: inicia sesión y, en sus primeros 7 días, vincula Telegram, registra una posición o visita la aplicación en
    3 días distintos. events = [(at, action)] del usuario. Devuelve el instante en que se cumplió la condición."""
    if first_login is None:
        return None
    end = first_login + 7 * DAY
    cands = []
    visit_days = []
    for at, action in sorted(events):
        if not (first_login <= at < end):
            continue
        if action in ("telegram_linked", "position_add"):
            cands.append(at)
        elif action == "visit":
            d = _day(at)
            if d not in visit_days:
                visit_days.append(d)
                if len(visit_days) == 3:
                    cands.append(at)
    return min(cands) if cands else None


def retained(visit_days, act_day, lo, hi, today):
    """None si la ventana [act_day+lo, act_day+hi] todavía no terminó; si no, True/False según haya alguna visita."""
    if today < act_day + dt.timedelta(days=hi):
        return None
    return any(act_day + dt.timedelta(days=lo) <= d <= act_day + dt.timedelta(days=hi) for d in visit_days)


CHANNELS = (("telegram", ("telegram",)), ("x", ("twitter", " x ", "x.com", "tuit")), ("reddit", ("reddit",)),
            ("youtube", ("youtube", "video")), ("referido", ("amig", "referi", "recomend", "conocid")),
            ("buscador", ("google", "busqu", "buscador")), ("landing", ("landing", "página", "pagina", "web")))


def channel(note):
    t = " " + (note or "").lower() + " "
    if not t.strip():
        return "sin dato"
    for name, keys in CHANNELS:
        if any(k in t for k in keys):
            return name
    return "otro"


# ------------------------------------------------------------------------------------------------ informe
def _load():
    users = db.all_("SELECT id, status, created_at, approved_at, request_note, telegram_chat_id, is_admin FROM users", ())
    users = [u for u in users if not u["is_admin"]]
    ids = {u["id"] for u in users}
    acts = db.all_("SELECT user_id, at, action FROM activity WHERE action IN "
                   "('login', 'visit', 'export_csv', 'telegram_linked', 'telegram_unlinked', 'position_add') "
                   "OR action LIKE 'tab:%'", ())
    ev = {}
    for a in acts:
        if a["user_id"] in ids:
            ev.setdefault(a["user_id"], []).append((float(a["at"]), a["action"]))
    surveys = db.all_("SELECT user_id, survey, answers, skipped, at FROM survey_responses", ())
    surveys = [s for s in surveys if s["user_id"] in ids]
    return users, ev, surveys


def report(now=None, data=None):
    """Informe agregado del piloto. Sin correos, nombres, IP ni notas: solo recuentos."""
    now = now or time.time()
    today = _day(now)
    users, ev, surveys = data if data is not None else _load()
    out = {"generado_utc": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(timespec="seconds"),
           "instrumentacion": {"metricas": enabled(), "encuestas": surveys_enabled()},
           "avisos": []}
    if not enabled():
        out["avisos"].append("Instrumentación apagada: no se registran visit, export_csv ni tab. Las métricas de uso "
                             "y retención no son interpretables hasta encenderla (requiere G-16 y autorización).")
    st = {}
    for u in users:
        st[u["status"]] = st.get(u["status"], 0) + 1
    approved = [u for u in users if u.get("approved_at")]
    out["solicitudes"] = {"total": len(users), "aprobadas": len(approved), "rechazadas": st.get("rejected", 0),
                          "pendientes": st.get("pending", 0)}
    out["canal_de_adquisicion"] = {}
    for u in users:
        c = channel(u.get("request_note"))
        out["canal_de_adquisicion"][c] = out["canal_de_adquisicion"].get(c, 0) + 1

    cohorts, per_user = {}, []
    for u in approved:
        e = ev.get(u["id"], [])
        logins = [at for at, a in e if a == "login"]
        first = min(logins) if logins else None
        act = activation(e, first)
        vdays = sorted({_day(at) for at, a in e if a == "visit"})
        rec = {"first": first, "act": act, "vdays": vdays,
               "tg": any(a == "telegram_linked" for _, a in e) or bool(u.get("telegram_chat_id")),
               "pos": sum(1 for _, a in e if a == "position_add"),
               "exp": sum(1 for _, a in e if a == "export_csv"),
               "tabs": [a[4:] for _, a in e if a.startswith("tab:")]}
        if act is not None:
            ad = _day(act)
            rec["r30"] = retained(vdays, ad, 22, 30, today)
            rec["r60"] = retained(vdays, ad, 52, 60, today)
        per_user.append(rec)
        if first is None:
            key = "sin inicio de sesión"
        else:
            y, w, _ = _day(first).isocalendar()
            key = f"{y}-S{w:02d}"
        cohorts.setdefault(key, []).append(rec)

    def block(recs):
        started = [r for r in recs if r["first"] is not None]
        act = [r for r in started if r["act"] is not None]
        pending_act = sum(1 for r in started if r["act"] is None and now < r["first"] + 7 * DAY)
        r30 = [r["r30"] for r in act if r.get("r30") is not None]
        r60 = [r["r60"] for r in act if r.get("r60") is not None]
        return {"aprobados": len(recs), "con_inicio_de_sesion": len(started),
                "activacion": rate(len(act), len(started) - pending_act, pending=pending_act,
                                   missing=len(recs) - len(started)),
                "retencion_30d": rate(sum(r30), len(r30), pending=len(act) - len(r30)),
                "retencion_60d": rate(sum(r60), len(r60), pending=len(act) - len(r60)),
                "telegram_vinculado": rate(sum(1 for r in act if r["tg"]), len(act))}

    out["cohortes"] = {k: block(v) for k, v in sorted(cohorts.items())}
    out["total"] = block(per_user)

    # uso
    dau = {}
    for r in per_user:
        for d in r["vdays"]:
            if (today - d).days < 30:
                dau[d.isoformat()] = dau.get(d.isoformat(), 0) + 1
    week = [r for r in per_user if sum(1 for d in r["vdays"] if (today - d).days < 7) >= 2]
    wdays = [sum(1 for d in r["vdays"] if (today - d).days < 7) for r in week]
    tabs = {}
    for r in per_user:
        for t in r["tabs"]:
            tabs[t] = tabs.get(t, 0) + 1
    out["uso"] = {"activos_diarios_ultimos_30_dias": dict(sorted(dau.items())),
                  "activos_semanales_ultimos_7_dias": len(week),
                  "dias_de_uso_por_activo_semanal": round(sum(wdays) / len(wdays), 2) if wdays else None,
                  "usuarios_con_posiciones": sum(1 for r in per_user if r["pos"]),
                  "posiciones_registradas": sum(r["pos"] for r in per_user),
                  "usuarios_que_exportan": sum(1 for r in per_user if r["exp"]),
                  "dias_con_exportacion": sum(r["exp"] for r in per_user),
                  "pestanas_usuario_dia": dict(sorted(tabs.items(), key=lambda x: -x[1]))}
    out["encuestas"] = survey_summary(surveys)
    out["compuerta_b"] = gate_b(out)
    return out


# ------------------------------------------------------------------------------------------------ encuestas
INTENT = ("seguro_si", "probable_si", "no_se", "probable_no", "seguro_no")
ELITE = ("historial_auditable", "alertas_personalizadas", "mas_activos", "api_webhook", "equipos", "soporte_prioritario")
SURVEYS = {
    "dia14": {"day": 14, "titulo": "Tu uso de Crypto Radar", "preguntas": [
        {"id": "utilidad", "tipo": "escala", "min": 1, "max": 5, "texto": "¿Qué tan útil te resulta Crypto Radar? (1 = nada, 5 = mucho)"},
        {"id": "para_que", "tipo": "texto", "texto": "¿Para qué lo usas?"},
        {"id": "sobra", "tipo": "texto", "texto": "¿Qué te sobra?"},
        {"id": "falta", "tipo": "texto", "texto": "¿Qué te falta?"}]},
    "dia30": {"day": 30, "titulo": "Precio", "preguntas": [
        {"id": "vw_muy_barato", "tipo": "usd", "texto": "¿A qué precio mensual sería tan barato que dudarías de su calidad?"},
        {"id": "vw_barato", "tipo": "usd", "texto": "¿A qué precio mensual te parecería una ganga?"},
        {"id": "vw_caro", "tipo": "usd", "texto": "¿A qué precio mensual empezaría a parecerte caro?"},
        {"id": "vw_muy_caro", "tipo": "usd", "texto": "¿A qué precio mensual sería demasiado caro para considerarlo?"},
        {"id": "pagaria", "tipo": "opcion", "opciones": list(INTENT),
         "texto": "Si Crypto Radar Pro costara US$15 al mes (o US$149 al año), ¿lo pagarías?"},
        {"id": "periodo", "tipo": "opcion", "opciones": ["mensual", "anual", "ninguno"], "texto": "¿Mensual o anual?"},
        {"id": "reemplaza", "tipo": "texto", "texto": "¿Qué herramienta dejarías de pagar o de usar si lo pagas?"}]},
    "dia45": {"day": 45, "titulo": "Una pregunta", "preguntas": [
        {"id": "decepcion", "tipo": "opcion", "opciones": ["muy", "algo", "nada"],
         "texto": "¿Cómo te sentirías si ya no pudieras usar Crypto Radar? (muy / algo / nada decepcionado)"}]},
    "dia60": {"day": 60, "titulo": "Funciones futuras", "preguntas": [
        {"id": "elite_orden", "tipo": "orden", "opciones": list(ELITE),
         "texto": "¿Cuáles de estas funciones pagarías aparte? Ordénalas de más a menos interesante (puedes dejar fuera las que no)."},
        {"id": "elite_otro", "tipo": "texto", "texto": "¿Alguna otra?"},
        {"id": "lista_interes", "tipo": "opcion", "opciones": ["si", "no"],
         "texto": "¿Quieres que te avisemos cuando abra Pro a US$15 al mes? (No es una reserva ni un pago.)"}]},
}
WINDOW_DAYS = 14                    # cada encuesta se ofrece durante 14 días desde su día


def _validate(survey, answers):
    if not isinstance(answers, dict):
        raise ValueError("respuestas no válidas")
    clean = {}
    for q in SURVEYS[survey]["preguntas"]:
        v = answers.get(q["id"])
        if v in (None, "", []):
            continue
        t = q["tipo"]
        if t == "escala":
            v = int(v)
            if not q["min"] <= v <= q["max"]:
                raise ValueError(q["id"])
        elif t == "usd":
            v = round(float(v), 2)
            if not 0 <= v <= 10000:
                raise ValueError(q["id"])
        elif t == "opcion":
            if v not in q["opciones"]:
                raise ValueError(q["id"])
        elif t == "orden":
            if not isinstance(v, list) or len(set(v)) != len(v) or any(x not in q["opciones"] for x in v):
                raise ValueError(q["id"])
        else:
            v = str(v)[:500]
        clean[q["id"]] = v
    return clean


def pending_survey(user, now=None):
    """La encuesta que le toca al usuario hoy, o None. Nunca se ofrece con las encuestas apagadas."""
    if not surveys_enabled() or not user or user.get("is_admin"):
        return None
    now = now or time.time()
    e = [(float(r["at"]), r["action"]) for r in db.all_(
        "SELECT at, action FROM activity WHERE user_id = ? AND action IN ('login', 'visit', 'telegram_linked', 'position_add')",
        (user["id"],))]
    logins = [at for at, a in e if a == "login"]
    act = activation(e, min(logins) if logins else None)
    if act is None:
        return None
    done = {r["survey"] for r in db.all_("SELECT survey FROM survey_responses WHERE user_id = ?", (user["id"],))}
    days = (now - act) / DAY
    for sid, s in SURVEYS.items():
        if sid not in done and s["day"] <= days < s["day"] + WINDOW_DAYS:
            return {"id": sid, **s}
    return None


def answer(user, survey, answers, skipped=False, now=None):
    if not surveys_enabled():
        raise ValueError("las encuestas no están activas")
    p = pending_survey(user, now)
    if not p or p["id"] != survey:
        raise ValueError("esta encuesta no está disponible")
    clean = {} if skipped else _validate(survey, answers)
    q = ("INSERT INTO survey_responses(id, user_id, survey, answers, skipped, at) VALUES (?, ?, ?, ?, ?, ?) "
         + ("ON CONFLICT (id) DO NOTHING" if db.IS_PG else ""))
    if not db.IS_PG:
        q = q.replace("INSERT INTO", "INSERT OR IGNORE INTO")
    rid = hashlib.sha256(f"{user['id']}|{survey}".encode()).hexdigest()[:32]
    db.execute(q, (rid, user["id"], survey, json.dumps(clean, ensure_ascii=False), 1 if skipped else 0, now or time.time()))
    return True


def van_westendorp(rows):
    """Rango de precio aceptable [PMC, PME] con las cuatro preguntas. rows = [(muy_barato, barato, caro, muy_caro)]."""
    rows = [r for r in rows if all(isinstance(x, (int, float)) for x in r)]
    n = len(rows)
    if not n:
        return {"muestra": 0, "rango_aceptable": None}
    grid = sorted({x for r in rows for x in r})
    too_cheap = lambda p: sum(1 for r in rows if r[0] >= p) / n
    not_cheap = lambda p: sum(1 for r in rows if r[1] < p) / n
    not_exp = lambda p: sum(1 for r in rows if r[2] > p) / n
    too_exp = lambda p: sum(1 for r in rows if r[3] <= p) / n
    pmc = next((p for p in grid if too_cheap(p) <= not_cheap(p)), None)
    pme = next((p for p in grid if too_exp(p) >= not_exp(p)), None)
    med = lambda i: sorted(r[i] for r in rows)[n // 2] if n % 2 else (sorted(r[i] for r in rows)[n // 2 - 1] + sorted(r[i] for r in rows)[n // 2]) / 2
    return {"muestra": n, "rango_aceptable": [pmc, pme] if pmc is not None and pme is not None else None,
            "medianas": {"muy_barato": med(0), "barato": med(1), "caro": med(2), "muy_caro": med(3)},
            "incluye_15": bool(pmc is not None and pme is not None and pmc <= 15 <= pme),
            "aviso": "muestra pequeña: no interpretar" if n < MIN_ACTIVATED else None}


def survey_summary(rows):
    by = {}
    for r in rows:
        by.setdefault(r["survey"], []).append(r)
    out = {}
    for sid in SURVEYS:
        rs = by.get(sid, [])
        ans = [json.loads(r["answers"] or "{}") for r in rs if not r["skipped"]]
        o = {"respuestas": len(ans), "omitidas": sum(1 for r in rs if r["skipped"])}
        if sid == "dia14":
            u = [a["utilidad"] for a in ans if "utilidad" in a]
            o["utilidad_media"] = round(sum(u) / len(u), 2) if u else None
        if sid == "dia30":
            pv = [a.get("pagaria") for a in ans if a.get("pagaria")]
            o["intencion_de_pago"] = rate(sum(1 for x in pv if x in ("seguro_si", "probable_si")), len(pv))
            o["periodo"] = {k: sum(1 for a in ans if a.get("periodo") == k) for k in ("mensual", "anual", "ninguno")}
            o["van_westendorp"] = van_westendorp([(a.get("vw_muy_barato"), a.get("vw_barato"), a.get("vw_caro"),
                                                   a.get("vw_muy_caro")) for a in ans])
        if sid == "dia45":
            dv = [a.get("decepcion") for a in ans if a.get("decepcion")]
            o["muy_decepcionado"] = rate(sum(1 for x in dv if x == "muy"), len(dv))
        if sid == "dia60":
            pts = {}
            for a in ans:
                order = a.get("elite_orden") or []
                for i, f in enumerate(order):
                    pts[f] = pts.get(f, 0) + (len(ELITE) - i)
            o["elite_puntos_borda"] = dict(sorted(pts.items(), key=lambda x: -x[1]))
            o["elite_elegida_por"] = {f: sum(1 for a in ans if f in (a.get("elite_orden") or [])) for f in ELITE}
            o["lista_de_interes"] = sum(1 for a in ans if a.get("lista_interes") == "si")
        out[sid] = o
    return out


def gate_b(rep):
    """Lectura automática de la compuerta B (DECISION_COMERCIAL_GO_NO_GO.md §2). No decide: informa."""
    t = rep["total"]
    n_act = t["activacion"]["numerador"]

    def zone(r, go, gray):
        v = r.get("tasa") if isinstance(r, dict) else None
        if v is None:
            return "sin datos"
        return "GO" if v >= go else "zona gris" if v >= gray else "NO-GO"
    s = rep["encuestas"]
    crit = {"B1_activacion": zone(t["activacion"], .50, .35), "B2_retencion_30d": zone(t["retencion_30d"], .35, .20),
            "B3_retencion_60d": zone(t["retencion_60d"], .25, .15),
            "B4_decepcion": zone(s["dia45"]["muy_decepcionado"], .40, .25),
            "B5_intencion_de_pago": zone(s["dia30"]["intencion_de_pago"], .30, .15)}
    if n_act < MIN_ACTIVATED:
        verdict = f"insuficiente: {n_act} activados (mínimo {MIN_ACTIVATED}); la regla es extender el piloto"
    elif crit["B2_retencion_30d"] == "NO-GO" or crit["B4_decepcion"] == "NO-GO":
        verdict = "NO-GO"
    elif all(crit[k] == "GO" for k in ("B1_activacion", "B2_retencion_30d", "B4_decepcion", "B5_intencion_de_pago")) \
            and "NO-GO" not in crit.values():
        verdict = "GO a la compuerta C (requiere además la compuerta A y la autorización del propietario)"
    else:
        verdict = "zona gris"
    return {"criterios": crit, "lectura": verdict,
            "nota": "B6 (lista de interés frente al punto de equilibrio) y B7 (Van Westendorp) se leen a mano con el informe."}
