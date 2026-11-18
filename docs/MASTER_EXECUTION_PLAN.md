# Plan maestro de ejecución · Crypto Radar 2.1

Fecha: 16 de noviembre de 2026, verificado entre las 06:20 y las 07:40 UTC.

**Objetivo inmediato:** dejar el piloto cerrado, gratuito y medible listo para abrir, de 60 a 90 días. **No** es lanzar ni cobrar. Nada de lo descrito aquí está desplegado ni fusionado.

**Etiquetas de estado.** No son equivalentes:

| Etiqueta | Significado |
|---|---|
| **IMPLEMENTADO** | Código escrito en una rama. |
| **PROBADO** | Pruebas automáticas ejecutadas en verde en esta sesión (SQLite y PostgreSQL 16 local). |
| **EN PR** | Pull request abierto, pendiente de revisión. |
| **DESPLEGADO** | En Render. **Ninguno de los cambios de hoy lo está.** |
| **VERIFICADO EN PRODUCCIÓN** | Comprobado en el servicio real después de desplegar. |
| **PENDIENTE DEL PROPIETARIO** | Solo PATRON puede hacerlo: consolas, credenciales, contratos o autorizaciones. |

## 1. Estado real verificado

| Elemento | Estado | Cómo se verificó |
|---|---|---|
| `main` | `d1cf246` (landing antigua) | `git fetch` |
| `release-2.1` | `2f6df27` | ídem |
| `production-2.0.0` | `9176b36` | ídem |
| `claude/investigacion-prospectiva` | `a976fa3` | ídem |
| Servicio `crypto-radar-2-1` | Rama `release-2.1`, autodeploy apagado, plan starter, 1 instancia, **sin health check**. `/healthz` responde 200; último escaneo a las 02:27 UTC | API de Render y `curl` |
| Registro de arranque de la 2.1 (02:27 y 02:34 UTC) | «Código de alta del administrador (CRYPTO_RADAR_ADMIN_ENROLL_TOKEN): **vigente**»: el TOTP del administrador **no está confirmado** | Registros de Render |
| Despliegue de la 2.1 | **Dos escaneos solapados** a las 02:25 (instancias `mf2br` y `qkmvd`): justifica el bloqueo de líder | Registros de Render |
| Servicio `crypto-radar` (2.0) | **Activo**: rama `production-2.0.0`, autodeploy apagado, health check `/healthz`, último escaneo a las 04:29 UTC. Cuesta US$7 al mes | API de Render y `curl` |
| Landing `crypto-radar-ventas` | Sirve la landing **antigua** de `main` | `curl` |
| Raíz pública de la 2.1 (`/`) | Sirve `web/landing.html`, que promete «100 cupos de fundador a US$12», «7 días de prueba sin tarjeta» y pagos con «tarjeta de cualquier país» y «USDT». **Hallazgo nuevo de hoy** | `curl` a `https://crypto-radar-2-1.onrender.com/` |
| Neon | **Sin acceso** desde esta sesión. Plan, CU-h, transferencia, almacenamiento y conexiones **sin medir** | — |
| Variables de entorno | No se leyeron valores (las reglas lo impiden). Solo se sabe lo que dicen los registros de arranque | — |
| Repositorio | Público | Sesiones anteriores; sin cambios |

**Pull requests abiertos** (ninguno fusionado; GitHub, 06:20 UTC):

| PR | Rama → base | Papel en este plan |
|---|---|---|
| #3 → #8 | Cadena de preparación del piloto (`claude/project-thread-i8udp5` … `claude/preparacion-piloto`) | Historial previo. **Ya está desplegado en la 2.1 vía `release-2.1`** pero sin fusionar en `main`. No se toca |
| #9 | `claude/investigacion-edge` → `claude/preparacion-piloto` | Investigación (NO EDGE). Contiene `INFORME_INVESTIGACION_EDGE.md` y `DECISION_FINAL_EDGE.md`, que no están en `release-2.1`. Separada del producto |
| **#11 = PR A** | `claude/landing-honesta` → `main` | Landing honesta |
| **#12 = PR B** | `claude/p1-fiabilidad-2-1` → `release-2.1` | Fiabilidad y seguridad de la 2.1 |
| **#13 = PR D** | `claude/project-thread-d8apbh` → `release-2.1` | Documentos y unit economics (solo `docs/` y `tests/test_economia.py`) |
| **#14 = PR C** | `claude/instrumentacion-piloto` → `release-2.1` | Instrumentación del piloto (apagada) |
| PR E | — | **No se crea.** Las mejoras de producto se deciden con los datos del piloto (§7) |

**Solapamientos comprobados:**

- **#11 y #12:** no comparten archivos. El #11 cambia `ventas/` en `main`; el #12 cambia `radar/` y `web/` en `release-2.1`. El #12 copia la landing del #11 en `web/landing.html`. Si el #11 cambia en la revisión, hay que volver a copiarla.
- **#12 y #14:** comparten `web/app.js`, `web/index.html`, `web/style.css`, `radar/db.py` y `radar/webapi.py`. Una fusión de prueba (#12 y luego #14 sobre `release-2.1`) entra **sin conflictos**, y con las dos juntas las suites dan 312 + 26 + 18 en verde.
- **#13:** solo documentos; no se solapa con código.

**Orden de fusión recomendado:** #12 → #14 → #13 en `release-2.1`, y #11 en `main` por separado. Si `main` vuelve a desplegar la 2.0, antes hay que confirmar que `crypto-radar` sigue en `production-2.0.0` (lo está, con autodeploy apagado).

## 2. Lo hecho hoy

| Cambio | PR | Estado |
|---|---|---|
| Landing: texto de transparencia exacto; solo Pro como «propuesta futura», US$15 o US$149 (12,42 al mes, 17,2 %); Élite «aplazado» sin precio ni botón; sin precio de referencia | #11, `64713cf` | IMPLEMENTADO · PROBADO (73/73, más 300–1500 px y botón ENTRAR) · EN PR |
| Lectura parcial de `latest.json` (`db.get_kv_fields`, extracción en SQL) para el sondeo de 30 s y `/healthz` | #12, `a48500e` | IMPLEMENTADO · PROBADO (SQLite, archivos y PostgreSQL 16) · EN PR |
| Líder único con comprobación en la base (`leader.confirm()`), keepalives TCP y `tcp_user_timeout` | #12, `289f150` | IMPLEMENTADO · PROBADO con 2 procesos reales: un solo líder, caída con SIGKILL, sesión terminada en la base y recuperación · EN PR |
| Atribución «Data provided by CoinGecko» con enlace y de alternative.me junto al Fear & Greed | #12, `289f150` | IMPLEMENTADO · PROBADO (pruebas y navegador) · EN PR |
| La raíz pública de la 2.1 deja de prometer cupos, prueba y pagos (copia de la landing honesta, con el script externo por la CSP) | #12, `289f150` | IMPLEMENTADO · PROBADO (sin errores de CSP en navegador) · EN PR |
| Instrumentación del piloto, métricas por cohorte con IC de Wilson, encuestas e informe para el administrador, **apagado** | #14 | IMPLEMENTADO · PROBADO (18 + 3, y 312 en la suite) · EN PR |
| Cálculo de caja corregido (7,904 meses → US$13.074), contribución frente a utilidad neta, cifras antiguas marcadas como SUSTITUIDO, prueba de cifras | #13 | IMPLEMENTADO · PROBADO (`tests/test_economia.py`) · EN PR |

Ya estaba en el #12 desde antes: `/livez`, readiness real en `/healthz` (503 en 3 s con la base caída), barra permanente de «señales no validadas» y estado público sin veredicto.

**Sobre la corrección de caja pedida.** La fórmula indicada, Σ desde t = 0 hasta 11 de 0,92^t, da **7,904**, no 7,34. El documento usa 7,904 con la derivación escrita. Mi cifra anterior, 7,92, también tenía un error de redondeo. Si se quería que el primer mes ya tuviera cancelación (t = 1 a 12), el resultado es 7,27 meses y unos US$12.505. Los dos casos están en `UNIT_ECONOMICS.md` §3 y en la prueba.

## 3. Defectos encontrados hoy

| # | Defecto | Gravedad | Estado |
|---|---|---|---|
| D-1 | La raíz pública de la 2.1 promete cupos de fundador, prueba de 7 días y pagos con tarjeta/USDT | CRÍTICO (honestidad comercial, en producción) | Corregido EN PR #12; **sigue en vivo** hasta desplegar |
| D-2 | Durante un despliegue, dos instancias escanean a la vez | ALTO | EN PR #12 |
| D-3 | Una conexión colgada podía mantener la marca de líder sin tener el candado | MEDIO | Corregido EN PR #12 (`confirm()` antes de cada trabajo) |
| D-4 | Sin atribución de CoinGecko ni de alternative.me | ALTO (licencia) | EN PR #12 |
| D-5 | El ejemplo de caja usaba 7,92 meses | BAJO (documento) | Corregido EN PR #13 |
| D-6 | OKX se usa como respaldo de velas y no figuraba en las licencias | MEDIO | Añadido a R-05 |
| D-7 | Los reembolsos no revocan el plan (R-09) | ALTO cuando haya pagos | PENDIENTE: no aplica mientras los pagos estén apagados |
| D-8 | `web/landing.js` y `web/vendor/*` quedan sin uso tras D-1 | BAJO | Se dejan; borrarlos es opcional en otra PR |

**Riesgo residual del líder.** Si un trabajo ya empezó cuando se corta la sesión, ese trabajo termina en la instancia vieja mientras la nueva puede empezar el suyo. El escaneo y el paper trading escriben el resultado completo, así que el último gana: no hay datos a medias, pero puede haber un escaneo repetido.

## 4. Matriz de bloqueos para abrir el piloto

El piloto se abre cuando `GO_NO_GO_PILOTO.md` esté en GO. **Hoy está en NO-GO.**

| Req. | Qué falta | Estado | Bloquea el piloto | Depende de |
|---|---|---|---|---|
| G-16 / R-12 | Texto legal de privacidad completo y revisado, que mencione el registro de uso | PENDIENTE DEL PROPIETARIO (y abogado) | **Sí** | — |
| R-18 | TOTP del administrador inscrito y `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` eliminado | PENDIENTE DEL PROPIETARIO | **Sí** | — |
| R-19 | Rotar la contraseña de `radar_app` y el token del bot de Telegram (los dos pasaron por el chat) | PENDIENTE DEL PROPIETARIO | **Sí** | R-24 (copia antes de rotar) |
| R-20 | Desplegar el #12 y poner `/healthz` como *health check* | EN PR + PENDIENTE DEL PROPIETARIO | **Sí** | Revisión del #12 |
| R-21, R-22 | Líder único y lectura parcial | EN PR | Sí (D-2) | ídem |
| R-23 | Confirmar el plan de Neon y medir el consumo | PENDIENTE DEL PROPIETARIO | **Sí** si es Free | — |
| R-24 | Copia automática cifrada fuera de Neon y una restauración probada | PENDIENTE (decisión de dónde guardar, §6) | **Sí** | Decisión |
| R-27 | Landing honesta publicada en las dos URL | EN PR (#11 y #12) | **Sí** (D-1) | Revisión |
| R-28 | Señales marcadas como no validadas | EN PR (#12) | Sí | ídem |
| R-31 | Instrumentación lista, apagada | EN PR (#14) | Sí, para medir | G-16 antes de encender |
| R-01, R-04, R-05 | Licencias de CoinGecko, Binance, Bybit y OKX | PENDIENTE DEL PROPIETARIO | **Sí**: el piloto gratuito también debe respetar las condiciones de los proveedores | Respuestas escritas |
| R-25 | Suspender la 2.0 después de preservar sus datos | PENDIENTE DEL PROPIETARIO | No (pero cuesta US$7 al mes y sigue escaneando) | Copia de la 2.0 |
| R-26 | Repositorio privado | PENDIENTE DEL PROPIETARIO | Recomendado antes del piloto | — |

Los requisitos **comerciales** (pagos, reembolsos, términos, impuestos, facturación) están en `REQUISITOS_LANZAMIENTO.md` y **no** bloquean el piloto gratuito.

## 5. Instrucciones para PATRON

Ninguna se ejecutó. Ninguna pide pegar secretos en el chat.

### R-18: TOTP del administrador

1. Entra en `https://crypto-radar-2-1.onrender.com/entrar` como `patron` y abre **Configuración → Cuenta → Verificación en dos pasos**.
2. Escanea el QR con tu app de autenticación y escribe el código de 6 dígitos y el código de alta que guardaste. El código de alta nunca va al chat.
3. Cierra sesión y vuelve a entrar: debe pedir el segundo factor.
4. **Solo después**, en Render, servicio `crypto-radar-2-1` → **Environment**, borra `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` y guarda (reinicia el servicio).
5. Avísame. Compruebo en los registros que ya no aparece «vigente» y que «Administrador: patron · verificado» sigue.

### R-19: rotación de credenciales

1. Antes, haz una copia (R-24, §6).
2. **Neon:** consola → proyecto → **Roles** → `radar_app` → **Reset password**. Copia la nueva cadena de conexión del endpoint **directo** (sin `-pooler`).
3. **Render:** en `crypto-radar-2-1` → **Environment**, reemplaza `DATABASE_URL` y guarda.
4. Comprueba que `/healthz` vuelve a 200. Tras el despliegue del #12, si la base falla devuelve 503.
5. **Telegram:** en BotFather, `/revoke` sobre `@cryptoradaria_bot`, y pega el token nuevo en `TELEGRAM_BOT_TOKEN` en Render. El anterior deja de funcionar al instante.
6. Recuperación: si la app no arranca, la contraseña anterior ya no sirve. Repite el paso 2 y vuelve a pegarla. No hay pérdida de datos.

### R-20: *health check*

Solo después de desplegar el #12: en `crypto-radar-2-1` → **Settings → Health Check Path** = `/healthz`.

### R-23: Neon

En la consola, **Billing** y **Monitoring** del proyecto `mute-sky-79699743`, anota:

- el plan;
- las CU-h del mes;
- la transferencia;
- el almacenamiento;
- las conexiones máximas.

Repite la lectura 3 días después de desplegar el #12. Si el plan es Free, la recomendación es Launch (unos US$19,70 al mes, estimado). No cambies el plan sin decidirlo.

### R-25: suspender la 2.0, preservando datos

1. Copia de la base de la 2.0 con `python main.py backup create` y `verify` (`PLAN_BACKUP_RECUPERACION.md` §1), desde tu equipo y con su `DATABASE_URL`.
2. En Render, `crypto-radar` → **Settings → Suspend service**. Suspender no borra nada y se puede reanudar.
3. No borres la base de la 2.0.

### R-26: repositorio privado

GitHub → repositorio → **Settings → General → Danger Zone → Change visibility → Private**. Render sigue funcionando porque usa la app de GitHub instalada.

## 6. Decisiones que necesita el propietario

1. **Dónde se guardan las copias automáticas (R-24).** El código de copia con HMAC ya existe (`main.py backup`); falta programarlo y guardarlo cifrado fuera de Neon. Opciones:
   - **(a) GitHub Actions programado**, con cifrado `age` y artefacto de 90 días. Cuesta US$0, pero exige el repositorio **privado** y secretos en GitHub.
   - **(b) Cron de Render** y almacenamiento S3 compatible (por ejemplo Cloudflare R2). Cuesta unos US$1 al mes más el almacenamiento, y hay que crear una cuenta.
   - **(c) Manual semanal** desde tu equipo, más el historial de Neon del plan Launch.

   Recomendación: **(a)** tras hacer el repositorio privado. Si no hay respuesta, preparo (a) en un PR **sin activarlo**.
2. **Definición de «activo»** en las ventanas de retención: al menos 1 día con `visit` (lo implementado) o al menos 2 días.
3. Autorizar la **revisión y fusión** de #12, #14, #13 y #11, y después el **despliegue** de la 2.1 y de la landing.
4. **Licencias:** escribir a CoinGecko (plan Basic: ¿el piloto gratuito ya es uso comercial?), Binance, Bybit y OKX.

## 7. Mejoras de producto (fase P2)

**Evaluadas, no implementadas.** Las reglas piden demostrar la necesidad primero; la encuesta del día 60 (en el #14) mide el interés por cada candidato.

| Mejora | Valor | Requisito previo | Medición de necesidad |
|---|---|---|---|
| Historial auditable de señales (fecha, activo, exchange, temporalidad, condiciones, precio, invalidación, objetivos hipotéticos, resultado posterior, caducidad, datos faltantes; inmutable, con los negativos) | Transparencia verificable | Tabla de solo inserción; nunca editar señales pasadas; «resultado hipotético», no rentabilidad | Encuesta del día 60 y uso de «Rendimiento» (`tab:perf`) |
| Alertas personalizadas (umbral por activo y métrica, límite de frecuencia, deduplicación) | Ahorro de tiempo | Medir antes el costo en Telegram y en la base; sin prometer entrega instantánea | Encuesta del día 60 y Telegram vinculado |
| Watchlist, panel de seguimiento, frescura, invalidación y exportaciones | UX | — | Encuesta del día 14 («qué falta») |

## 8. Pruebas ejecutadas (resultados reales, 16-nov-2026)

| Suite | Rama | Resultado |
|---|---|---|
| `tests/test_suite.py` (PostgreSQL 16 + SQLite) | #12 | 309/309 |
| `tests/test_suite.py` | #14 | 312/312 |
| `tests/test_fiabilidad.py` (incluye 2 procesos reales) | #12 | 26/26, tres corridas seguidas |
| `tests/test_piloto.py` | #14 | 18/18 |
| `tests/test_edge.py` y `tests/test_paper.py` | #12 y #14 | 29/29 y 39/39 |
| #12 + #14 fusionados en local | — | 312 + 26 + 18 |
| `tests/ventas/prueba_landing_honesta.js` | #11 | 73/73 |
| `prueba_boton_entrar.js` y `prueba_anchos_encabezado.js` | #11 | OK (300–1500 px) |
| `tests/test_economia.py` | #13 | 9/9 |

**Fallos durante el trabajo, todos corregidos:**

- Una prueba de código fuente esperaba el texto antiguo del planificador de paper trading.
- La expresión de «ventaja afirmada» marcaba «Sin ventaja demostrada».
- La prueba HTTP contaba el evento `access_requested`.
- PostgreSQL local se paró y se reinició.

No se desactivó ni se debilitó ninguna prueba.

**No probado:** nada en Render ni en Neon real, porque no hay despliegue ni acceso. Las pruebas de carga locales **no** demuestran capacidad en Render.

## 9. Costos actualizados

- **Gasto en Render (MEDIDO por plan):** US$7 de la 2.1 + US$7 de la 2.0 = **US$14 al mes**. Suspender la 2.0 ahorra US$7.
- **Neon:** PENDIENTE de leer en la consola.
- **Estimación para operar cobrando:** US$61,70 al mes. Se mantiene de `UNIT_ECONOMICS.md`: Render, CoinGecko Basic y Neon Launch estimado.
- **Sin cotizar:** abogado, contador, licencias de Binance, Bybit y OKX.

## 10. Veredictos

- **Piloto: NO-GO hoy.** Faltan G-16, R-18, R-19, R-20, R-23, R-24, las licencias y el despliegue de #11 y #12.
- **Comercial: NO-GO.** Sin datos de demanda (`DECISION_COMERCIAL_GO_NO_GO.md`).

## 11. Próximas acciones

1. **PATRON:** R-18, R-23 y revisar #12, #14, #11 y #13. Decidir el §6.1.
2. **Equipo, tras la decisión:** PR de copias automáticas sin activar; volver a copiar la landing si el #11 cambia.
3. **PATRON:** autorizar el despliegue. Después: R-20, R-19 y la verificación en producción (sin «vigente» en los registros, `/healthz` con la base sana, raíz sin promesas, un solo «Instancia líder» en los registros).
4. **Con G-16 cerrado:** encender `CRYPTO_RADAR_PILOT_METRICS`, abrir el piloto por tandas y seguir `PLAN_PILOTO_90_DIAS.md`.


## 12. Auditoría correctiva independiente (16–18 nov 2026)

Informe completo: `AUDITORIA_CORRECTIVA_2026-11-16.md`.

| Hallazgo | PR | Estado |
|---|---|---|
| H1 activación sobre aprobados elegibles | #14 | Corregido y probado |
| H2 intención de pago sobre elegibles a 30 días | #14 | Corregido y probado |
| H3 fencing transaccional por generación | #12 | Corregido y probado (con reinicio real de PG16) |
| H4 endpoint directo frente al pooler | #12 | Corregido; falta la confirmación del propietario (R-23) |
| H5 respaldos independientes | #15 (nueva) | Código listo y **desactivado**; faltan las decisiones del propietario |
| H6 costos por etapa | #13 | Corregido |
| H7 privacidad de la instrumentación | #14 | Corregido; falta G-16 |

Orden de fusión propuesto, sin cambios: #12 → #14 → #13. La #15 es independiente. **Ninguna fusión ni despliegue sin
autorización escrita.** Veredicto del piloto: **NO-GO**. Veredicto comercial: **NO-GO**.
