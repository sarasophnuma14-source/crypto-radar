# Auditoría integral de Crypto Radar · Fase cero

Fecha de la inspección: 16 de noviembre de 2026, 04:07 a 04:40 UTC.
Alcance: repositorio, ramas, PR, servicios de Render (solo lectura), servicios en vivo (peticiones públicas), código de la 2.1, landing comercial, pruebas y dependencias.
Esta fase no modificó ningún servicio, variable, rama de producción ni base de datos.

> Regla de lectura: cada hallazgo lleva la evidencia que lo respalda. Lo que no se pudo comprobar está marcado **NO VERIFICADO** con el motivo. Nada aquí afirma que el sistema sea seguro: solo describe lo que se inspeccionó.

---

## 1. Estado real verificado

### 1.1 GitHub

| Elemento | Esperado (informe previo) | Real (16-nov 04:10 UTC) | Coincide |
|---|---|---|---|
| `main` | d1cf246 | d1cf246 (merge PR #10) | Sí |
| `release-2.1` | 2f6df27 | 2f6df27 | Sí |
| `production-2.0.0` | 9176b36 | 9176b36 | Sí |
| `claude/investigacion-prospectiva` | a976fa3 | a976fa3, sin PR | Sí |
| `claude/preparacion-piloto` | — | cb3a357 (2 commits de informes por delante de release-2.1) | — |
| Visibilidad del repositorio | pública | **pública** (API de GitHub: `private: false`) | Sí |
| Colaboradores | — | 1 (el propietario, admin) | — |

PR abiertos: #3 → #4 → #5 → #6 → #7 → #8 (cadena apilada que llevó a release-2.1, ninguno fusionado) y #9 (borrador, investigación edge v3). Cerrados y fusionados: #1, #2 y #10.
Consecuencia: el código de la 2.1 en producción **no está en `main`**. `main` contiene la 2.0 más la carpeta `ventas/`.

### 1.2 Render (workspace del propietario)

| Servicio | Rama | Auto-deploy | Plan | Health check | Estado |
|---|---|---|---|---|---|
| crypto-radar-2-1 | release-2.1 | apagado | starter | **vacío** | activo, /healthz 200 en 0,67 s |
| crypto-radar (2.0) | production-2.0.0 | apagado | 0.5 CPU / 512 MB | /healthz | **activo, no suspendido**; último escaneo 00:27 UTC |
| crypto-radar-ventas (estático) | main, `./ventas` | apagado | estático | — | activo |

Último despliegue de la 2.1: 02:34 UTC. Memoria en reposo 110 a 147 MB de 512 MB. CPU casi nula fuera del escaneo.

### 1.3 Neon

**NO VERIFICADO directamente**: esta sesión no tiene conector ni credenciales de Neon, y no debe tenerlas. Evidencia indirecta en los registros de Render: a las 02:19 la 2.1 falló al arrancar con `password authentication failed for user 'radar_app'`; desde las 02:22 arranca con `esquema verificado` contra el endpoint directo `ep-polished-lake-…` (sin `-pooler`).

### 1.4 Pruebas y dependencias (en esta sesión, rama release-2.1)

- `tests/test_suite.py` con PostgreSQL 16 real: **309 pruebas, OK, 0 omitidas** (48,7 s, Python 3.13). Producción usa Python 3.12.7.
- `tests/test_edge.py`: 29 OK. `tests/test_paper.py`: 39 OK.
- `pip-audit -r requirements.txt` (psycopg 3.3.9, numpy 2.5.3, pandas 3.0.5): **sin vulnerabilidades conocidas**.
- Avisos: sockets y conexiones SQLite sin cerrar en las pruebas (`ResourceWarning`); no afecta a producción.

---

## 2. Mapa de arquitectura

```
                         Internet
                            │
         ┌──────────────────┼──────────────────────────┐
         │                  │                          │
 crypto-radar-ventas   crypto-radar-2-1            crypto-radar (2.0)
 (estático, main/ventas) (Python stdlib, 1 proceso)  (production-2.0.0, sigue activo)
  - landing comercial    ┌─────────────────────────┐   - escanea cada 4 h
  - botón ENTRAR ───────▶│ PooledHTTPServer 16 hilos│   - consume API de mercado
  - lista de espera      │  /  (landing duplicada)  │
    que NO guarda        │  /entrar  /app  /admin   │
                         │  /privacidad /aviso      │
                         │  /healthz (sin auth)     │
                         ├─────────────────────────┤
                         │ hilo planificador:       │
                         │  escaneo cada 4 h        │
                         │  vigilancia precio 15 min│
                         │  memecoins cada hora     │
                         │  paper trading diario    │
                         │ hilo Telegram (polling)  │
                         └───────────┬─────────────┘
                                     │ psycopg (1 conexión por hilo, sin pool)
                                     ▼
                       Neon PostgreSQL 16 (Frankfurt)
                       esquema app: users, sessions, activity, positions,
                       payments, telegram_links, kv (documentos JSON),
                       rate_limits, admin_enroll_tokens, platform_meta,
                       legacy_archive
 Proveedores externos: CoinGecko (global, mercados), Binance (spot, funding, velas, libros),
 Bybit (respaldo), alternative.me (miedo y codicia), Telegram Bot API.
 Pagos: Wompi y NOWPayments implementados pero CRYPTO_RADAR_PAYMENTS=off.
```

Investigación (aislada del producto): `research/edge3` (v3, holdout usado una vez y bloqueado), `research/prospectivo` (rama aparte, 0 hipótesis registradas), `radar/edge` y `radar/paper_trading` (dentro del producto, solo D_volmom_L28 en papel).

## 3. Inventario funcional: implementado frente a prometido

| Función | Estado real en 2.1 | Lo que dice la landing en vivo |
|---|---|---|
| Escaneo de mercado cada 4 h | Implementado. Último: 150 mercados CoinGecko, 518 pares Binance, velas de 70 activos, 25 libros | "Escaneo cada 4 horas" ✔ |
| Puntaje 0-100, fases, entrada, stop, TP | Implementado. **Pesos no validados** (IC negativo dentro y fuera de muestra) | Presentado como herramienta ✔, sin marcar como experimental ✖ |
| Early Entry / Explosive Momentum / Exit Intelligence | Implementado como reglas heurísticas | Descritos ✔ |
| On-chain / ballenas | **N/D** (sin fuente gratuita verificable) | No se promete de forma explícita ✔ |
| Alertas Telegram por usuario | Implementado, sin reintentos ni registro de entrega; prueba de extremo a extremo pendiente | "Alertas a Telegram" ✔ (no verificada en real) |
| Vigilancia de precio cada 15 min | Implementado para **todos** los planes de pago | Vendido como exclusivo de Élite ✖ |
| "Backtest de cualquier token" | **No existe**. Élite solo ve resultados estáticos ya calculados | Vendido en Élite ✖ |
| "Watchlist sin límite" | Hay watchlist en ajustes, **limitada a 50 activos en todos los planes** (`radar/auth.py:575`) | Vendido como exclusivo de Élite ✖ |
| "Informe semanal y soporte por chat" | Hay resumen semanal por Telegram; **no hay soporte por chat** | Vendido en Élite ✖ |
| "Diario de señales con resultados" / "historial público" | Diario privado dentro del panel, exportable a CSV en todos los planes; **no hay historial público** | "cada señal queda registrada … en un historial público" ✖ |
| Plan Libre | Ranking de 3 activos | "Top 5 con 24 h de retraso, boletín semanal" ✖ |
| Pagos con tarjeta y USDT | Implementados, **apagados**, nunca probados en sandbox real | "aceptamos tarjetas de cualquier país. También USDT" ✖ |
| Cupos de fundador, prueba de 7 días | **No existen** en el código | "100 cupos de fundador a US$12", "7 días de prueba" ✖ |
| Lista de espera | El formulario **no guarda nada** (mensaje "todavía no guarda correos") | CTA principal ✖ |
| Solicitud de acceso con consentimiento | Implementado en `/entrar` de la 2.1, guarda en Neon, aprobación del admin | No enlazado desde la landing ✖ |
| Pro frente a Élite | Diferencia real: solo `backtest: True` (resultados estáticos) | Cinco diferencias anunciadas ✖ |

## 4. Hallazgos

Escala: CRÍTICO impide operar de forma segura · ALTO riesgo importante o defecto funcional · MEDIO experiencia, mantenimiento o rendimiento · BAJO mejora incremental.
Esfuerzo: S (< 2 h), M (medio día), L (1 a 3 días), XL (más).

### CRÍTICOS

**C-1. La landing pública promete cosas que no existen y oferta precios que no se pueden contratar.**
- Evidencia: `ventas/index.html` en `main` (servido en crypto-radar-ventas): líneas 225, 338-353, 366 ("100 cupos de fundador", "7 días de prueba sin tarjeta", "aceptamos tarjetas de cualquier país. También USDT", "Backtest de cualquier token", "Watchlist sin límite", "soporte por chat"). La misma copia vive en `web/landing.html` y se sirve en `https://crypto-radar-2-1.onrender.com/`.
- Impacto: publicidad engañosa y escasez ficticia; riesgo legal y reputacional en una plataforma financiera. Contradice las reglas 1 y 12 del proyecto.
- Probabilidad: ya ocurre (página en vivo).
- Solución: rediseño de la landing (fase cinco) con funciones reales únicamente, precios marcados como "propuesta de lanzamiento pendiente de aprobación", CTA de interés y sin cupos ni pruebas gratuitas.
- Esfuerzo: L. Prueba: test automático que falle si la página contiene "cupos", "fundador", "prueba gratis", "aceptamos tarjetas" o "USDT" como medio activo; revisión manual de la matriz de funciones.

**C-2. La landing destaca resultados retrospectivos positivos que la investigación posterior no respalda.**
- Evidencia: `ventas/index.html:312-313` muestra "+31,3 %" (memecoins, holdout mirado antes de un ajuste) y "+18,8 %" (RSI2) con contador animado. La ronda v3 (35 configuraciones, `docs/DECISION_FINAL_EDGE.md` en la rama de investigación) concluyó **NO EDGE** en las 8 familias.
- Impacto: sugiere una ventaja estadística que no está demostrada. Contradice el principio de transparencia.
- Solución: sustituir por la sección de transparencia pedida ("no se ha demostrado una ventaja estadística consistente fuera de muestra"), con enlace a un resumen honesto de las pruebas, incluidas las negativas.
- Esfuerzo: S (dentro de C-1). Prueba: test que verifica que la página contiene la frase de transparencia y no contiene porcentajes de retorno destacados.

**C-3. El segundo factor del administrador no consta como activado y el código de alta sigue vigente.**
- Evidencia: registros de Render del arranque de las 02:34 UTC: `Código de alta del administrador (CRYPTO_RADAR_ADMIN_ENROLL_TOKEN): vigente`. Desde ese arranque no hay registros de aplicación. El código (`radar/auth.py:769-780`) bloquea toda acción de administración hasta que el TOTP esté activo, así que no existe una vía administrativa sin TOTP; pero mientras el código siga vigente, quien tenga la contraseña del admin y ese código puede inscribir su propio teléfono.
- **NO VERIFICADO**: si PATRON ya inscribió el TOTP después de las 02:34 (requiere iniciar sesión como admin; esta sesión no debe usar esas credenciales).
- Solución: PATRON inscribe el TOTP en `/app`, comprueba que la acción de administración funciona y borra `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` en Render. Recuperación documentada en `docs/BOOTSTRAP_ADMIN.md §4` (`CRYPTO_RADAR_ADMIN_RESET=1`).
- Esfuerzo: S (propietario). Prueba: tras redesplegar, el registro debe decir que el código no está definido; un intento de administración sin TOTP debe responder 403.

**C-4. Credenciales que pasaron por el chat sin constancia de rotación.**
- Evidencia: memoria del proyecto y nota del coordinador: la contraseña de `radar_app` y el token del bot de Telegram se compartieron en la conversación. No hay registro de rotación. El fallo de autenticación de las 02:19 muestra que la contraseña sí se cambió una vez durante el despliegue, pero no después de la exposición.
- **NO VERIFICADO**: estado actual de ambas credenciales (esta sesión no puede ni debe leer secretos).
- Solución: rotar la contraseña con `ALTER ROLE radar_app PASSWORD …` en la consola de Neon y actualizar `DATABASE_URL` en Render; revocar el token con `/revoke` en @BotFather y poner el nuevo en `TELEGRAM_BOT_TOKEN`. Ambas cosas las hace PATRON, nunca pegándolas en el chat.
- Esfuerzo: S. Prueba: arranque con `esquema verificado`; `getMe` con el token viejo debe devolver 401; el bot responde `/ayuda` con el nuevo.

### ALTOS

**A-1. Render no tiene health check en la 2.1.**
- Evidencia: `healthCheckPath: ""` en el servicio srv-dbt67erbc2fs73d7s74g. Render solo comprueba que el puerto abra.
- Impacto: un proceso colgado, o sin base de datos, sigue recibiendo tráfico; los despliegues no se detienen si la app arranca rota.
- Además, `/healthz` responde siempre `"ok": true` cuando el proceso contesta. Lee `latest.json` de Neon, así que si la base cae devuelve 500 (indirectamente sí detecta la base), pero no detecta un planificador muerto ni un escaneo atrasado.
- Solución: (1) PATRON configura `/healthz` en Render (el conector no puede). (2) Código: separar `/healthz` (liveness, barato, sin base) y `/readyz` (readiness: `SELECT 1` con tiempo límite, edad del último escaneo, hilo del planificador vivo), sin exponer detalles. Hoy `/readyz` cae en la ruta autenticada y responde 401.
- Esfuerzo: M. Prueba: unitaria con base caída (503), escaneo de más de 9 h (estado degradado), respuesta sin secretos, tiempo < 1 s.

**A-2. La 2.0 sigue activa y escaneando.**
- Evidencia: servicio crypto-radar `suspended: not_suspended`; `/healthz` 200 con último escaneo 00:27 UTC.
- Impacto: costo mensual de un segundo servicio de pago; superficie de ataque con un sistema que ya no se mantiene; posible bot de Telegram antiguo (@RadarCrypto2026_bot) enviando alertas.
- Solución: procedimiento de suspensión (inventario de variables, confirmación de que no hay datos que conservar en disco efímero, suspender, verificar). Requiere autorización.
- Esfuerzo: S. Prueba: servicio `suspended`, URL devuelve la página de servicio suspendido, la 2.1 no cambia.

**A-3. No hay copias de seguridad automáticas.**
- Evidencia: `radar/backup.py` tiene `create|verify|compare|restore` con HMAC, pero solo se ejecuta a mano; el planificador (`radar/server.py:scheduler`) no programa copias. `docs/INFORME_BACKUP_REAL.md` registra una copia manual.
- Impacto: pérdida de cuentas y diario si se borra o corrompe la base. La recuperación de Neon depende de la ventana de historia del plan, **NO VERIFICADA**.
- Solución: cron job de Render diario (`main.py backup create` + `verify`) hacia almacenamiento separado, retención 7 diarias + 4 semanales, alerta si falla, restauración de prueba mensual a una rama temporal de Neon. Requiere decidir dónde se guardan (costo) y autorización para crear el cron.
- Esfuerzo: L. Prueba: restauración completa en una base vacía con `compare` sin diferencias.

**A-4. Repositorio público con documentación interna de infraestructura.**
- Evidencia: API de GitHub `visibility: public`; `docs/CONFIGURACION_NEON_2_1.md` y `docs/INFORME_DESPLIEGUE_2_1_REAL.md` incluyen identificadores del proyecto Neon, del endpoint y de los roles. Búsqueda en todo el historial: no se encontraron secretos reales (solo valores de prueba).
- Impacto: facilita el reconocimiento; expone toda la lógica y la investigación.
- Solución: hacerlo privado (Render seguirá desplegando si su app de GitHub tiene acceso; hay que comprobarlo antes). Requiere autorización; no se borra historial.
- Esfuerzo: S. Prueba: `private: true`; un despliegue manual de prueba de `crypto-radar-ventas` funciona.

**A-5. Política de privacidad publicada como borrador con 10 marcadores COMPLETAR, y se recoge consentimiento sobre ella.**
- Evidencia: `https://crypto-radar-2-1.onrender.com/privacidad` contiene la cadena COMPLETAR 10 veces (responsable, NIT, domicilio, representante, correo, teléfono, plazos de borrado y conservación). El texto sí avisa "Borrador pendiente de revisión legal". `POLICY_VERSION 2026-11-15` se acepta al solicitar acceso.
- Impacto: consentimiento sobre una política sin responsable identificado (Ley 1581 de 2012 en Colombia exige identificar al responsable). No se deben inventar datos.
- Solución: documento de datos faltantes para PATRON y abogado; mientras tanto, banner visible de borrador y no abrir solicitudes al público general.
- Esfuerzo: S (preparación) + tiempo legal externo.

**A-6. Pro y Élite son prácticamente iguales en el código.**
- Evidencia: `radar/auth.py:45-50`. Pro y Élite comparten `ranking_limit 20`, Telegram, cartera, salidas y memecoins. Élite añade solo `backtest` (resultados estáticos).
- Impacto: no hay base para cobrar US$29 frente a US$15 hoy. Los precios internos (`billing.status`: 19/190 y 39/390) además no coinciden con la propuesta nueva (15/149 y 29/299).
- Solución: matriz de planes basada en funciones reales (fase cuatro) y, si se aprueba, desarrollo de diferenciadores con costo estimado.

**A-7. Las señales del motor se presentan sin marca de "no validado".**
- Evidencia: el panel muestra entrada, stop, TP1-TP3 y veredicto ("OPORTUNIDADES ACTIVAS" también en el endpoint público `/api/public/status`). El único aviso es genérico (`web/index.html:229`). El motor tiene Sharpe fuera de muestra −0,30 (v3).
- Impacto: un usuario que paga puede interpretar las señales como validadas.
- Solución: etiqueta de estado por señal ("Señal analítica · no validada estadísticamente"), fecha de generación, vencimiento y datos faltantes; quitar el veredicto del endpoint público.
- Esfuerzo: M. Prueba: test de interfaz que exige la etiqueta en cada tarjeta.

### MEDIOS

| Id | Hallazgo | Evidencia | Solución | Esfuerzo |
|---|---|---|---|---|
| M-1 | Telegram sin reintentos ni registro de entrega; un fallo solo resta del contador | `radar/telegram_bot.py:38-44, 140-151` | Tabla de entregas idempotente (alerta, usuario, estado, intentos), reintento con espera, métrica de fallos | M |
| M-2 | Dos instancias simultáneas durante cada despliegue: ambas escanearon (02:25 y 02:27) y ambas hacen polling de Telegram (conflicto 409 posible) | Registros de Render 02:23-02:27 | Candado en base (`pg_try_advisory_lock`) para escaneo, paper trading y polling | M |
| M-3 | La app usa el endpoint directo de Neon, no el pooler; una conexión por hilo (16) sin pool | `docs/CONFIGURACION_NEON_2_1.md:114`, `radar/db.py:130-156` | Evaluar `-pooler` (requiere autorización para cambiar `DATABASE_URL`); medir conexiones activas | S |
| M-4 | Landing duplicada: `ventas/index.html` (main) y `web/landing.html` (2.1) divergen | diff de 214 líneas | Una sola fuente; la 2.1 redirige `/` a la landing o la sirve desde el mismo archivo | S |
| M-5 | La lista de espera no guarda correos, pero ya existe un flujo de solicitud con consentimiento en `/entrar` | `ventas/index.html:426-431`, `radar/auth.py` (request) | CTA "Solicitar acceso" hacia `/entrar#solicitar`; sin recoger datos en la landing | S |
| M-6 | Precio de BTC fijo en la landing ("≈ US$68.200") | `ventas/index.html:236` | Quitar o leer de `/api/public/status` con fecha | S |
| M-7 | ~~Texto "Se actualiza cada hora" incorrecto~~ **Retirado tras verificar**: está en la pestaña de memecoins, que sí se revisa cada hora (`MEME_EVERY_S`) | `web/app.js:442` | Ninguna | — |
| M-8 | El código de la 2.1 vive en una cadena de 6 PR sin fusionar; `main` no refleja producción | §1.1 | Plan de integración (ya existe `docs/PLAN_INTEGRACION_GIT.md`), solo con autorización | M |
| M-9 | Login móvil: el formulario queda muy abajo | Informe del hilo anterior; capturas en `boton-entrar/movil_login.png` | Reordenar en pantallas estrechas | S |

### BAJOS

| Id | Hallazgo | Solución |
|---|---|---|
| B-1 | `ResourceWarning` de sockets y SQLite en las pruebas | Cerrar recursos en `tearDown` |
| B-2 | Pruebas locales en Python 3.13; producción en 3.12.7 | Ejecutar la suite también con 3.12 en cada PR |
| B-3 | Registros sin formato estructurado ni latencias por endpoint | Una línea JSON por petición lenta o error, sin datos personales |
| B-4 | Sin CI en GitHub | Workflow con la suite (SQLite + PG en servicio) |

## 5. Motores analíticos: qué son y qué no son

| Motor | Qué calcula | Estado de validación |
|---|---|---|
| Early Entry | Acumulación, consolidación, volumen relativo, divergencias, distancia al máximo | **Señal analítica**. No validada |
| Explosive Momentum | Aceleración de precio, volumen anormal, ruptura | **Señal analítica**. No validada |
| Exit Intelligence | Distribución, divergencias bajistas, pérdida de soportes, stops | **Señal analítica**. No validada |
| Puntaje 0-100 | Combinación ponderada | IC negativo dentro y fuera de muestra: **pesos no validados** |
| D_volmom_L28 | Momentum ajustado por volatilidad | **Hipótesis experimental** en paper trading (mínimo 183 días) |
| Investigación prospectiva | 13 criterios, puntos de control a 90/183/365 días | 0 hipótesis registradas |

Ninguna señal cumple hoy los criterios para llamarse "validada estadísticamente".

## 6. Plan priorizado

### P0 · Bloqueos de seguridad y producción (antes de cualquier usuario externo)

| # | Acción | Quién | Necesita autorización |
|---|---|---|---|
| P0-1 | Inscribir TOTP del admin y borrar `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` (C-3) | PATRON | — |
| P0-2 | Rotar contraseña de `radar_app` y token de Telegram (C-4) | PATRON | — |
| P0-3 | Poner `/healthz` como health check en Render (A-1) | PATRON | — |
| P0-4 | Retirar de la landing promesas falsas, escasez y resultados positivos (C-1, C-2) | Claude, PR a `main` | Publicar = fusionar y desplegar |
| P0-5 | Suspender la 2.0 (A-2) | Claude o PATRON | **Sí** |
| P0-6 | Repositorio privado (A-4) | PATRON | **Sí** |

### P1 · Fiabilidad esencial, bajo riesgo

| # | Acción | Rama |
|---|---|---|
| P1-1 | `/healthz` liveness + `/readyz` readiness (A-1) | desde release-2.1 |
| P1-2 | Etiqueta "no validada" y frescura en cada señal; quitar veredicto público (A-7) | desde release-2.1 |
| P1-3 | Candado de instancia única para escaneo, paper y Telegram (M-2) | desde release-2.1 |
| P1-4 | Registro de entregas y reintentos de Telegram (M-1) | desde release-2.1 |
| P1-5 | Copias automáticas diarias con verificación (A-3) | requiere decidir almacenamiento |
| P1-6 | Documento de datos faltantes de privacidad (A-5) | docs |
| P1-7 | Textos y móvil (M-6, M-9) | desde release-2.1 / main |

### P2 · Experiencia y diferenciación comercial

Landing premium completa (fase cinco), matriz Pro/Élite real, análisis de costos y pricing, benchmark con fuentes fechadas, CI.

### P3 · Escalabilidad

Pool de conexiones, separar el escáner en un worker solo si las mediciones lo justifican, métricas por endpoint.

### P4 · Experimental

Nuevas hipótesis solo mediante pre-registro en `research/prospectivo`, nunca en el producto.

## 7. Lo que esta fase no hizo

- No cambió Render, Neon, variables ni ramas de producción.
- No leyó secretos ni inició sesión como administrador.
- No comprobó el plan ni la ventana de recuperación de Neon (sin acceso).
- No hizo benchmark externo ni cálculo de costos todavía: van en las fases cuatro y once, con fuentes y fecha.
