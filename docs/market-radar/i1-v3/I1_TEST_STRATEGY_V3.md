# I-1 v3 · Estrategia de pruebas

Fecha: 18-nov-2026. Sustituye §6 del plan v2. **Ninguna de estas pruebas existe ni se ha ejecutado.** Los únicos resultados citados son EXP (consultas SQL desechables del 18-nov) y se marcan como tales.

## 1. Reglas generales

1. PostgreSQL **16** real, local, solo por socket Unix; una base nueva por módulo de prueba, creada desde `template0` con el modelo de roles de `I1_LEDGER_REDESIGN.md` §2. Las pruebas de PostgreSQL fallan (no se omiten) si no hay servidor.
2. Toda la suite corre dentro de un espacio de red sin interfaces salvo loopback (`I1_SECURITY_THREAT_MODEL.md` §5).
3. Python 3.12 y 3.13. `unittest`, como la suite de la 2.1. Sin dependencias nuevas.
4. Cada prueba adversarial ejecuta el ataque real y comprueba el **error concreto** (código SQLSTATE o mensaje), no solo que «falló algo».
5. Las pruebas de concurrencia tienen **control negativo**: el mismo ensayo contra una variante deliberadamente defectuosa debe fallar; si no falla, la prueba no detecta nada y se considera inválida.
6. Evidencia exigida para aceptar: salida completa en Python 3.12 y 3.13, versión de PostgreSQL, semillas aleatorias usadas, y el inventario de privilegios generado.

## 2. Grupos

| Grupo | Objetivo | Escenarios principales | Resultado esperado | Evidencia | Aceptación | Casos |
|---|---|---|---|---|---|---|
| **TS-UNIT** (tipos, tiempo, hash, validadores) | Lógica pura correcta | Tiempos sin zona; `Decimal` desde texto; codificación `c2` (escala decimal, `-0`, nulos, campos que cambian el hash); reglas DQ con `price_domain` | Mismos valores → mismo hash; cualquier campo de significado distinto → hash distinto | Salida | 100 % | 40 |
| **TS-SRC** (selección de fuente) | Determinismo | Primaria, respaldo por licencia/uso/cuarentena, `NO_SOURCE`, límites semiabiertos, `source_switch`, empates rechazados por la base | Una sola decisión por entrada; motivos correctos | Salida | 100 % | 10 |
| **TS-CAL** (calendarios) | Fronteras correctas | Sesión que cruza medianoche; pausa intradía; festivo; media sesión; cambio de hora EE. UU. y Europa (semanas desfasadas); hora local inexistente y ambigua; D1 de sesión; vela parcial; alineación `utc_clock` vs `session_open` | Fronteras iguales a las tablas de referencia escritas a mano para el calendario ficticio | Salida | 100 % | 12 |
| **TS-DATA** (contrato universal) | No excluir mercados | Precio negativo con `price_domain = any` aceptado y con `positive` marcado; volumen nulo con `none`; `NaN`/`Infinity` rechazados; escala > `price_scale` rechazada; futuro sin vencimiento rechazado; índice negociable rechazado | Según la tabla de `I1_DATA_CONTRACT_REVIEW.md` | Salida | 100 % | 8 |
| **TS-RAW** (crudos) | Fidelidad | Bytes idénticos (espacios, orden de claves, `1.10`, `1e-7`); claves duplicadas → rechazo con cuerpo guardado; no UTF-8; > 8 MiB; hash recalculado en la base; `payload_id` ajeno; huella sin parámetros secretos; purga | Byte a byte igual; rechazos con motivo | Salida + hash | 100 % | 10 |
| **TS-MIG** (migraciones, PG16) | Reversibilidad demostrable | `up` desde vacío; inventario de catálogo igual al manifiesto; `down` hasta vacío sin restos; `up` otra vez; `btree_gist` preexistente queda; objeto ajeno dependiente → `down` aborta sin borrar nada; objeto no inventariado en `mr` → aborta; `down` en instancia no `test` → rechazo; checksum alterado (up y down); fallo a mitad de una migración → nada aplicado; dos runners a la vez; versión ≠ 16 → rechazo | Catálogo antes = después en ida y vuelta; ningún objeto ajeno tocado | Volcado de catálogo antes/después | 100 % | 12 |
| **TS-PRIV** (permisos) | Mínimo privilegio | Inventario de privilegios por rol contra lista blanca; atributos de rol; `PUBLIC` sin `EXECUTE`, `CONNECT`, `TEMP`; funciones `SECURITY DEFINER` con `search_path` fijo (consulta a `pg_proc.proconfig`); dueño de todo = `mr_owner` | Cualquier privilegio fuera de la lista → fallo | Inventario generado | Lista blanca exacta | 10 |
| **TS-ADV** (adversariales) | Ataques de `I1_LEDGER_REDESIGN.md` §8 y T-01…T-14 | Los 14 ataques del ledger + sombra en `pg_temp` + funciones internas + `mr_owner` sin desactivar disparadores + verificación de cadena tras alteración como superusuario | Error concreto en cada uno; la cadena detecta la alteración | SQLSTATE por caso | 14/14 | 14 |
| **TS-CONC** (concurrencia) | Reproducibilidad bajo carga | N escritores (8 y 32) con pausas dentro de la transacción; 10 % rollbacks; terminación forzada de conexiones; lectores REPEATABLE READ guardando (W, H, hash); relectura posterior; contador sin huecos; H registrado; **control negativo** con marca `MAX(hora)` | 100 % relecturas idénticas; versiones confirmadas sin huecos; control negativo con ≥ 1 diferencia | Registro de cada (W, H, hash) | 100 % y control negativo detecta | 8 |
| **TS-REC** (recuperación) | Sin estado parcial | Caída durante `publish`; caída entre preparar y publicar; `idle_in_transaction_session_timeout` corta y libera; reintento idempotente; limpieza de lotes huérfanos; reinicio del servidor a mitad de una carga | Ninguna versión parcial; reintentos sin duplicados | Salida + `ops_events` | 100 % | 6 |
| **TS-REPRO** (reproducibilidad temporal) | Pregunta (W, T) | Escenarios 1–9 de `I1_TEMPORAL_MODEL.md`; (W, H) inválidas rechazadas; comparación con implementación de referencia en memoria con 1.000 historias aleatorias (semilla fija); análisis estático: ninguna lectura de tablas base fuera de `_asof` | Igualdad exacta con la referencia | Semillas y diferencias (0) | 100 % | 8 |
| **TS-LIC** (licencias) | Matriz de `I1_LICENSE_ENFORCEMENT.md` §2 | Recepción y publicación sin licencia (dos capas); vencida; revocada; otro mercado; sin `store`; `retention_until`; lectura tras terminación por cada `post_termination`; funciones puras de mostrar/alertar/exportar/derivar con audiencia, territorio, retraso, atribución; desconocido → restrictivo | Según matriz | Salida | 100 % | 20 |
| **TS-LIC-SYN** (sintéticas) | Frontera §4 del modelo de amenazas | Licencia sintética sobre mercado real (por restricción); mercado sintético creado por `mr_writer`; funciones sintéticas en instancia `production`; cambiar `namespace`; cambiar `mr.instance.kind`; rol `mr_test_fixtures` ausente; nombre `zz-test-` en un mercado `real` (debe ser posible y no dar privilegios) | Rechazo en cada caso salvo el último, que demuestra que el nombre ya no importa | SQLSTATE | 100 % | 8 |
| **TS-NET** (red y conexión) | Ningún tráfico fuera | DSN con `hostaddr`, multi-host, `service`, `passfile`, host relativo, `PGHOST`/`PGHOSTADDR`/`PGSERVICE` en el entorno → rechazo antes de conectar; `inet_server_addr()` nulo; control dentro del espacio de red: conexión a 192.0.2.1 y resolución de un nombre público fallan | Rechazos y control negativo | Salida + configuración del espacio de red | 100 % | 8 |
| **TS-ISO** (aislamiento de la 2.1) | La 2.1 no cambia | `git diff --name-status release-2.1...HEAD` solo altas en carpetas permitidas; importaciones en ambos sentidos; terceros solo `psycopg`; `requirements.txt`, `render.yaml`, `main.py`, `web/`, `radar/` idénticos; suite de la 2.1 con el mismo número de pruebas y resultado que en la base | Sin diferencias | Salida de `git` y de la suite 2.1 | 100 % | 5 |
| **Total** | | | | | | **≈ 179** |

## 3. Criterios transversales

- Ningún caso «omitido» en la ejecución que se presenta como evidencia.
- Las pruebas de concurrencia se ejecutan al menos 3 veces con semillas distintas; las tres deben pasar.
- Cualquier prueba que pase contra la variante defectuosa del control negativo invalida su grupo.

## 4. Lo que estas pruebas no demuestran

- Ausencia total de errores en las funciones privilegiadas.
- Rendimiento con volúmenes reales (no hay datos reales en I-1).
- Que las licencias reales sean suficientes.
- Seguridad frente a administradores de base (solo detección).
