# Auditoría correctiva independiente · Crypto Radar 2.1

Fecha: 16–18 de noviembre de 2026. Alcance: PR #11, #12, #13 y #14, más una PR nueva, la #15. Primero se auditó, después
se corrigió y al final se demostró con pruebas.

**Nada se fusionó ni se desplegó.** No se tocaron secretos, variables de producción, Neon, precios del backend, el motor
cuantitativo, el paper trading ni el holdout. No se borró ni se debilitó ninguna prueba: las que cambiaron lo hicieron
porque cambió la definición que comprueban, y quedaron más estrictas.

**Veredicto del piloto: NO-GO.** Esta auditoría quita defectos, pero no cierra ninguno de los bloqueos que dependen del
propietario. Que las pruebas locales pasen no es un GO.

## 1. Hallazgos

### H1 · Activación con un denominador que excluía usuarios
Gravedad: **ALTA**, porque inflaba la métrica de la compuerta B1.

- **Evidencia.** En la PR #14, `radar/piloto.py` `report().block()` calculaba
  `rate(activados, con_inicio_de_sesion − pendientes)`. Los aprobados que nunca entraban quedaban como `sin_datos`,
  fuera del denominador. Además, las cohortes se agrupaban por la semana del primer inicio de sesión, con un balde
  aparte llamado «sin inicio de sesión».
- **Corrección.**
  - La ventana de 7 días se cuenta **desde la aprobación**.
  - Cada aprobado está en uno de tres estados: activado, no activado o pendiente (`activation_state`). Hay una sola
    definición, compartida por cohortes y total.
  - Elegibles = aprobados − pendientes.
  - Las cohortes se agrupan por semana de aprobación.
  - El informe muestra aprobados, elegibles, pendientes, activados, no activados (y cuántos de ellos nunca entraron)
    y bajas por supresión.
  - Solo sale del denominador quien tenga un motivo explícito, contado aparte: la cuenta eliminada.
- **Pruebas.** `tests/test_piloto.py` `ActivacionH1`, casos 1 a 8 tal como se pidieron. Además,
  `Informe.test_cohortes_separadas_y_tasas_con_ic` comprueba que la suma de las cohortes cuadra con el total en cada
  campo.

### H2 · Intención de pago calculada solo entre quienes respondían
Gravedad: **ALTA**, porque la no respuesta inflaba B5.

- **Evidencia.** `survey_summary` calculaba `intencion_de_pago = «sí» ÷ respuestas`, y `gate_b` usaba esa tasa.
- **Corrección.** Nueva función `payment_intent`:
  - Elegibles a 30 días = activados con al menos una visita en los días 22 a 30.
  - El informe da: respondieron, no respondieron, pendientes (encuesta aún abierta), participación, tasa sobre
    elegibles y tasa entre respondientes. Las respuestas de usuarios no elegibles se cuentan aparte.
  - **B5 usa la tasa sobre elegibles.** Omitir la encuesta o retirar la respuesta cuenta como «no sí».
  - Si la participación baja del 50 %, el informe muestra un aviso.
- **Pruebas.** `IntencionDePagoH2`, 7 pruebas:
  - participaciones de 100 %, 75 %, 50 %, 30 % y 25 %;
  - 0 respuestas;
  - ventana de encuesta todavía abierta;
  - respuestas de no elegibles.
  - Con la misma señal real, la lectura es siempre la misma. Con 8 «sí» de 10 respuestas y 40 elegibles, el resultado
    es 20 % y queda en zona gris, no 80 % y GO.

### H3 · El fencing del líder no era transaccional
Gravedad: **CRÍTICA**. Era posible perder o mezclar resultados durante un despliegue.

- **Evidencia.** En la PR #12, `confirm()` consultaba `pg_locks` justo antes del escaneo. Una instancia que perdía el
  candado a mitad del escaneo seguía escribiendo después. En los registros de Render del 16-nov a las 02:25 se vieron
  escaneos duplicados, en las instancias mf2br y qkmvd.
- **Corrección.**
  1. Tabla `leader_epoch` con una generación monotónica que aumenta en cada adquisición del candado.
  2. `leader.job()` fija esa generación para el hilo.
  3. `db.upsert_kv`, por donde pasan todas las escrituras de fondo, hace en **una sola transacción**: leer la
     generación con `FOR SHARE`, comparar y escribir. Si la generación está vencida, lanza `StaleLeader` y no escribe
     nada.
  4. El incremento del nuevo líder espera a que terminen esas transacciones. Desde que se confirma, toda escritura con
     una generación anterior se rechaza.
  5. Escaneo, memecoins, vigilancia de precios, escaneo manual y paper trading corren dentro de `leader.job()`. El motor
     de paper trading no se tocó.
  6. Las alertas de Telegram se registran con una escritura protegida **antes** de enviarse.
- **Pruebas.** `tests/test_fiabilidad.py` `FencingGeneracion`, 7 pruebas. Un disparador de PostgreSQL registra cada
  escritura confirmada junto con la generación vigente. Las pruebas son:
  1. dos procesos compitiendo;
  2. pérdida del candado a mitad de un escaneo: la fase 2 del escaneo se rechaza;
  3. recuperación del nuevo líder tras un SIGKILL;
  4. escritura tardía del líder antiguo;
  5. generación vencida y generación futura;
  6. **reinicio real de PostgreSQL** (`pg_ctl restart -m fast`);
  7. corte de la conexión dentro de la transacción, con dos casos: reintento que escribe una sola vez, y rechazo si
     otro tomó el relevo.

  Invariantes que se comprueban: ninguna escritura confirmada lleva una generación distinta de la vigente, y la
  generación nunca baja. La suite se pasó 3 veces seguidas sin fallos.

### H4 · Endpoint directo frente al pooler de Neon
Gravedad: **MEDIA**.

- **Evidencia.**
  - El candado del líder, el `SET client_encoding` y el `pg_advisory_lock`/`unlock` del arranque son de sesión, y el
    pooler de Neon (PgBouncer en modo transacción) no los admite.
  - `preflight` solo **avisaba** si la URL era del pooler.
  - `/healthz` abría una conexión TLS nueva en cada comprobación.
- **Corrección.**
  - El líder usa siempre el endpoint directo (`leader_url`), con una URL propia opcional
    (`CRYPTO_RADAR_LEADER_DATABASE_URL`).
  - `preflight` **falla** si la URL lleva `-pooler`.
  - Aviso al arrancar, antes de `init()`, sin mostrar la URL.
  - La comprobación de salud usa un único hilo y una única conexión persistentes, y abandona una comprobación colgada
    a los 30 s.
  - Nuevo documento `docs/ARQUITECTURA_CONEXIONES_NEON.md`: límites de Neon con su fuente, unas 23 conexiones por
    instancia, unas 46 durante un despliegue solapado y una regla de dimensionamiento.
  - `DATABASE_URL` de producción no se cambió.
- **Pruebas.** `ConexionesNeon` (3) y `T24_Preflight.test_pooler_de_neon_es_fallo`.

### H5 · Respaldos dependientes de la misma cuenta que el repositorio
Gravedad: **ALTA**.

- **Evidencia.** La recomendación anterior era GitHub Actions + age, sin almacenamiento independiente, sin simulacro
  periódico, sin alertas y sin custodia de claves.
- **Corrección.** PR #15, todo desactivado:
  - cifrado age con dos destinatarios públicos;
  - almacenamiento S3 compatible o carpeta, fuera de GitHub y Render;
  - la clave del job solo puede escribir;
  - relectura de lo subido;
  - latido externo, que también detecta el silencio;
  - simulacro en una base vacía;
  - retención 14/8/12;
  - procedimiento documentado de recuperación de claves.
- **Pruebas.** `tests/test_respaldo_externo.py`, 12 pruebas, sobre SQLite y sobre PostgreSQL 16.

### H6 · Costos mezclados entre etapas
Gravedad: **MEDIA**.

- **Evidencia.** `UNIT_ECONOMICS.md` §6 sumaba en un solo «total mínimo» un supuesto (Neon Launch) y dejaba fuera
  Render 2.0, que sigue activo.
- **Corrección.** Cinco tablas separadas:
  - **Gasto actual verificado: US$14 al mes** (Render 2.1 y 2.0). Neon y la cuota del workspace quedan pendientes, no
    en cero.
  - **Estimación del piloto: US$7 a 49 al mes** más pendientes.
  - **Estimación de comercialización: US$61,70**, marcada como ESTIMACIÓN.
  - Costos variables.
  - Costos sin cotizar.
  - Sigue en pie que la contribución no es utilidad neta.
- **Pruebas.** `tests/test_economia.py` `test_costos_separados_por_etapa`.

### H7 · Privacidad de la instrumentación y de las encuestas
Gravedad: **ALTA**, porque la política no mencionaba lo que se registra.

- **Evidencia.**
  - `web/privacidad.html` no describía los eventos de uso ni las encuestas.
  - El texto libre se guardaba tal cual.
  - El usuario no podía retirar sus respuestas.
  - Al eliminar una cuenta, sus respuestas quedaban huérfanas.
  - No había ningún plazo de retención.
  - Además, **`/api/admin/piloto` fallaba en PostgreSQL**: el `%` literal del `LIKE 'tab:%'` rompía psycopg. Las
    pruebas anteriores solo usaban datos inyectados.
- **Corrección.**
  - El texto libre se guarda sin correos, enlaces, teléfonos ni usuarios @ (`redact`).
  - Botón «Retirar mis respuestas»: se vacía el contenido y la respuesta cuenta como no respuesta.
  - Al eliminar una cuenta se borran sus datos del piloto y queda una baja anónima por cohorte.
  - `purge()` con un plazo que fija el propietario. Sin plazo no borra nada y el informe lo avisa.
  - El informe del administrador es solo agregado.
  - Nueva fila en la política de privacidad, con el plazo como `COMPLETAR`.
  - El patrón del `LIKE` va ahora como parámetro.
  - Nuevo documento `docs/PRIVACIDAD_INSTRUMENTACION.md`.
- **Pruebas.** `PrivacidadH7`, 8 pruebas. Además, toda la suite del piloto corre ahora también sobre PostgreSQL 16
  (`PILOTO_TODO_EN_PG=1`).

## 2. Resultados de las pruebas (ejecutadas en este entorno)

| PR | Suite | SQLite | PostgreSQL 16 |
|---|---|---|---|
| #12 | `test_suite.py` | 310 OK (5 omitidas) | 310 OK |
| #12 | `test_fiabilidad.py` | 36 OK (13 omitidas: necesitan PG) | 36 OK (incluye el reinicio real) |
| #12 | `test_paper.py`, `test_edge.py` | 39 OK, 29 OK | — |
| #14 | `test_suite.py` | 312 OK (5 omitidas) | 312 OK |
| #14 | `test_piloto.py` | 41 OK (1 omitida) | 41 OK (suite completa en PG) |
| #14 | `test_paper.py`, `test_edge.py` | 39 OK, 29 OK | — |
| #15 | `test_suite.py` | 309 OK (5 omitidas) | 309 OK |
| #15 | `test_respaldo_externo.py` | 12 OK | 12 OK |
| #13 | `test_economia.py` | 10 OK | — |

Todo es local, con PostgreSQL 16 en 127.0.0.1. **Nada se ejecutó contra Neon ni contra Render.**

## 3. Acciones que dependen del propietario

1. **R-23:** confirmar en la consola de Neon que `DATABASE_URL` usa el endpoint directo (sin `-pooler`), y anotar el
   plan, el cómputo y el consumo real.
2. **G-16:** completar los datos del responsable y los plazos de `web/privacidad.html`, incluido el de los datos del
   piloto. Revisión de un abogado.
3. Fijar `CRYPTO_RADAR_PILOT_RETENTION_DAYS` con el mismo plazo que la política.
4. Decidir si alguien leerá el texto libre de las encuestas por consulta directa y, si es así, declararlo en la
   política.
5. Respaldos (PR #15):
   - elegir el proveedor de almacenamiento y el de latidos;
   - activar el bloqueo de objetos;
   - crear las claves de solo escritura, lectura y borrado;
   - generar las dos identidades age y elegir quién custodia la segunda;
   - elegir la máquina que ejecuta las copias;
   - crear un rol de solo lectura en Neon;
   - hacer el primer simulacro manual.
6. **R-25:** suspender la 2.0 después de respaldarla, porque cuesta US$7 al mes mientras siga activa.
7. **R-18 y R-19:** TOTP del administrador y después borrar `ENROLL_TOKEN`; rotar `radar_app` y el token de Telegram.
8. **R-20:** `healthCheckPath = /healthz` en Render, después de desplegar la PR #12.
9. Licencias de datos: CoinGecko (también para el piloto gratuito), Binance, Bybit y OKX.
10. Revisar las PR #11, #12, #13, #14 y #15 y autorizar por escrito su fusión y su despliegue. Orden propuesto:
    #12 → #14 → #13; #15 es independiente.
11. Autorizar por escrito y por separado `CRYPTO_RADAR_PILOT_METRICS` y `CRYPTO_RADAR_PILOT_SURVEYS`, después de G-16.

## 4. Tabla final

| HALLAZGO | GRAVEDAD | ESTADO ANTERIOR | CAMBIO | PRUEBA | RESULTADO | PENDIENTE DEL PROPIETARIO |
|---|---|---|---|---|---|---|
| H1 Activación | Alta | Denominador sin los que nunca entraban; cohorte por primer inicio de sesión | Ventana desde la aprobación; tres estados; elegibles = aprobados − pendientes; cohorte por aprobación | `ActivacionH1` 1–8 | 8/8 OK en SQLite y PG16 | Ninguno técnico; encender métricas solo tras G-16 |
| H2 Intención de pago | Alta | «Sí» ÷ respondientes | B5 = «sí» ÷ elegibles a 30 días; participación, no respuesta y tasa entre respondientes por separado | `IntencionDePagoH2` (7) | 7/7 OK | Encender encuestas tras G-16 |
| H3 Fencing | Crítica | `confirm()` antes del trabajo; escrituras tardías posibles | Generación monotónica y comprobación en la misma transacción que la escritura | `FencingGeneracion` 1–7 | 7/7 OK, 3 veces seguidas, con reinicio real de PG | Autorizar despliegue de la PR #12 |
| H4 Directo frente al pooler | Media | Preflight solo avisaba; una conexión por cada comprobación de salud | Líder siempre por el endpoint directo; preflight falla con pooler; aviso al arrancar; salud con una conexión | `ConexionesNeon` (3), `T24…pooler` | OK | R-23: confirmar endpoint y plan |
| H5 Respaldos | Alta | GitHub Actions + age, misma cuenta | Almacenamiento externo, age con 2 claves, simulacro, latidos, retención; desactivado | `test_respaldo_externo` (12) | 12/12 OK en SQLite y PG16 | Proveedores, claves, máquina, rol de solo lectura, simulacro, activación |
| H6 Costos | Media | Un total que mezclaba un supuesto y omitía la 2.0 | Gasto actual US$14, piloto 7–49, comercialización 61,70 estimada, variables y sin cotizar por separado | `test_costos_separados_por_etapa` | OK | Costo real de Neon; cotizaciones legales, contables y operativas |
| H7 Privacidad | Alta | Política sin la instrumentación; texto libre crudo; sin retirada, supresión ni retención; informe roto en PG | Minimización; retirada; supresión; `purge`; política actualizada; corrección del `LIKE` | `PrivacidadH7` (8) + suite en PG | OK | G-16, plazo de retención, revisión jurídica |
