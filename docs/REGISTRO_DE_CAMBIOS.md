# Registro de cambios · Crypto Radar 2.1

**Despliegue.** Solo lo marcado como DESPLEGADO está en Render. Todo lo demás vive en pull requests sin fusionar.

## 16 de noviembre de 2026

### Desplegado

**2.1.0** (`release-2.1` @ `2f6df27`), en vivo desde las 02:22 UTC:

- plataforma nueva sin acceso heredado;
- administrador único;
- piloto cerrado con aprobación manual;
- pagos apagados.

Proviene de la cadena de PR #3 a #8. Ver `ESTADO_LANZAMIENTO_2_1.md`.

### En revisión (no desplegado)

**PR #11, landing honesta** (`claude/landing-honesta` → `main`)

| Commit | Cambio |
|---|---|
| `06b2312` y siguiente | Landing reescrita con funciones reales y transparencia. Sin cupos, sin prueba gratuita, sin pagos y sin rentabilidades pasadas |
| `64713cf` | Texto de transparencia exacto. Solo Pro como propuesta futura (US$15 o US$149, 17,2 %). Élite aplazado, sin precio. Sin precio de referencia. Prueba de 73 comprobaciones |

**PR #12, fiabilidad y seguridad de la 2.1** (`claude/p1-fiabilidad-2-1` → `release-2.1`)

| Commit | Cambio |
|---|---|
| Inicial | `/livez`; `/healthz` con readiness real (503 con la base caída o el planificador mudo); bloqueo de líder; barra de señales no validadas; estado público sin veredicto |
| `a48500e` | Lectura parcial de `latest.json` en SQL: el sondeo de 30 s y `/healthz` ya no descargan el informe |
| `289f150` | `leader.confirm()` comprueba en la base el candado antes de cada trabajo, con keepalives TCP. Atribución de CoinGecko y de alternative.me. La raíz pública de la 2.1 deja de prometer cupos, prueba y pagos |

**PR #14, instrumentación del piloto** (`claude/instrumentacion-piloto` → `release-2.1`)

- Eventos diarios idempotentes, apagados por defecto.
- Métricas por cohorte con IC de Wilson.
- Encuestas de los días 14, 30, 45 y 60.
- Informe para el administrador.
- Tabla `survey_responses`.

**PR #13, documentos** (`claude/project-thread-d8apbh` → `release-2.1`)

| Commit | Cambio |
|---|---|
| `ea36778` a `029d140` | Auditoría integral, costos, pricing, matriz de planes y benchmark |
| `3dfa43a` | `UNIT_ECONOMICS`, `MODELO_NEGOCIO_VALIDADO`, `PLAN_PILOTO_90_DIAS`, `DECISION_COMERCIAL_GO_NO_GO`, `REQUISITOS_LANZAMIENTO` |
| Este | `MASTER_EXECUTION_PLAN`, este registro, corrección del ejemplo de caja (7,904 meses, US$13.074), contribución frente a utilidad neta, cifras antiguas marcadas como SUSTITUIDO y `tests/test_economia.py` |

### Correcciones de documentos

| Documento | Antes | Ahora |
|---|---|---|
| `UNIT_ECONOMICS.md` §3 | 7,92 meses, US$13.090 | 7,904 meses, US$13.074, con la derivación |
| `ANALISIS_COSTOS_Y_RENTABILIDAD.md` §2 a §5 | Cifras con la mezcla Pro/Élite | Se conservan, marcadas como SUSTITUIDO |
| `ESTRATEGIA_PRICING.md` | Fila de Élite con 29/299 | Tachada: aplazado sin precio |
| `REQUISITOS_LANZAMIENTO.md` | 15 bloqueantes | 13 bloqueantes y 9 en PR. R-05 incluye OKX. EN PR no cuenta como cerrado |

## 15 de noviembre de 2026 y anteriores

Ver la descripción de los PR #1 a #10 en GitHub y los documentos:

- `AUDITORIA_PRODUCCION.md`
- `AUDITORIA_FINAL_PILOTO.md`
- `AUDITORIA_ESTRES_INTEGRAL.md`
- `CIERRE_RIESGOS_PILOTO.md`
- `GO_NO_GO_PILOTO.md`
