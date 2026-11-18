# I-1 v3 · Modelo de amenazas y controles

Fecha: 18-nov-2026. Resuelve V3-02, V3-06, V3-11 y recoge los controles de V3-01, V3-04.
Alcance: el núcleo I-1 (biblioteca, CLI, PostgreSQL 16 local). Sin UI, red ni proveedores reales.

## 1. Activos que se protegen

1. Integridad de la historia publicada (velas, metadatos, licencias).
2. Reproducibilidad de cualquier lectura con (W, H).
3. Que ningún dato llegue a un uso que su licencia no permite.
4. Que nada de I-1 toque la 2.1, Neon, Render ni la red.
5. Que una reversión no destruya objetos ajenos.

## 2. Actores

| # | Actor | Capacidad supuesta |
|---|---|---|
| 1 | Usuario de la aplicación | Llama a la CLI o a la biblioteca con entradas arbitrarias |
| 2 | SQL con privilegios limitados | Credenciales de `mr_writer` o `mr_reader` (filtradas o inyección) |
| 3 | Conexión de base abierta | Ejecuta cualquier sentencia que el rol permita, en transacciones propias |
| 4 | Transacciones concurrentes | Muchas sesiones a la vez, pausas, bloqueos |
| 5 | Datos malformados | Controla los bytes que devuelve un proveedor (o el sintético en una prueba) |
| 6 | Interrupciones | Termina conexiones o procesos en cualquier punto |
| 7 | Configuración de proveedores | Puede proponer filas de proveedores, fuentes o licencias por la vía normal |
| — | Fuera de alcance de prevención | `mr_owner`, `mr_migrator`, superusuario, administrador del host: solo **detección** (cadena de hashes) |

## 3. Casos adversariales

| Id | Amenaza | Precondición | Procedimiento | Resultado esperado | Protección | Prueba |
|---|---|---|---|---|---|---|
| T-01 | Escritura no autorizada | Actor 2 como `mr_writer` | `INSERT/UPDATE/DELETE/TRUNCATE` en tablas versionadas | `permission denied` | Privilegios (solo `mr_owner`) + disparadores | TS-ADV-01, 03, 10 |
| T-02 | Falsificación de secuencia | Actor 2/3 | `set_config('mr.write_seq', …)`; avanzar `ledger_head`; insertar en `write_log` | Rechazado | No hay variable de sesión en el control; sin privilegios en `ledger_head`/`write_log` | TS-ADV-02, 05, 06 |
| T-03 | Manipulación de marca de agua | Actor 1/3 | Pasar (W, H) inventados a `*_asof`; H con números > W o negativos | Validación: H ⊆ [1, W]; W ≤ máximo publicado; si no, error | Validación en `*_asof` | TS-REPRO-06 |
| T-04 | Corrupción del historial | Actor 3 / `mr_owner` por error | `UPDATE` de una fila publicada | Writer: `permission denied`; owner: error del disparador; superusuario con disparadores apagados: la verificación de la cadena falla | Permisos + disparadores + cadena de hashes | TS-ADV-03, 13, 14 |
| T-05 | Licencia sintética sobre mercado real | Actor 2/7 | Registrar licencia sintética que cubra un mercado `real`; crear un mercado «sintético» en una base de producción | Rechazado por restricción y por rol | §4 | TS-LIC-SYN-01…08 |
| T-06 | Lectura sin autorización | Actor 2 como `mr_writer` | `SELECT` de tablas base; lectura de crudos | `permission denied`; crudos solo vía función que comprueba licencia y purga | Privilegios; funciones de lectura | TS-PRIV-05, TS-LIC-05 |
| T-07 | Alteración de payloads | Actor 2/5 | Publicar un lote cuyo `body_sha256` no coincide con el cuerpo; reutilizar `payload_id` ajeno | `publish` recalcula el hash en la base (`sha256()` de PG16) y rechaza; el lote solo puede referenciar cuerpos de su preparación | Validación en `publish` | TS-RAW-03, 07 |
| T-08 | Inyección de dependencias | Actor 1 / desarrollador | Importar `radar/`, un paquete de terceros nuevo, o código de `tests/` desde `market_radar` | La prueba de fronteras falla; `requirements.txt` sin cambios | Análisis estático de importaciones; lista blanca | TS-ISO-01…05 |
| T-08b | Sombra de objetos en `search_path` | Actor 2 con `TEMP` | Crear `pg_temp.write_log` | Sin efecto | `SET search_path = pg_catalog, pg_temp` y nombres calificados; `TEMP` revocado | TS-ADV-11 |
| T-09 | Conexión remota | Actor 1 / entorno | DSN con `hostaddr`, `PGHOSTADDR`, `PGSERVICE`, multi-host, nombre que resuelve fuera | Rechazo antes de conectar; además, sin ruta de red | §5 | TS-NET-01…08 |
| T-10 | Borrado accidental de objetos | Desarrollador / runner | `down` con objetos ajenos dependientes; `down` en una base con datos reales | `down` aborta | Manifiesto, sin `CASCADE`, `down` solo en instancia `test` | TS-MIG-04…09 |
| T-11 | Mezcla de proveedores | Actor 7 | Dos fuentes con la misma prioridad; lectura de serie que cambia de proveedor | Restricción de exclusión; `source_switch` marcado | Exclusión + contrato de lectura | TS-SRC-04, 09 |
| T-12 | Reproducción inconsistente | Actor 4/6 | Lecturas durante publicaciones concurrentes, rollbacks y conexiones terminadas | 100 % de relecturas idénticas; H registrado | Contador sin huecos + (W, H) | TS-CONC-01…08 |
| T-13 | Denegación de servicio por bloqueo | Actor 2/4 | Abrir `publish` y no confirmar; tomar candados consultivos | La sesión se corta por `idle_in_transaction_session_timeout`; los candados consultivos no afectan (no se usan) | Tiempos límite; bloqueo de fila solo vía función | TS-REC-02, TS-ADV-09 |
| T-14 | Respuesta gigante o malformada | Actor 5 | Cuerpo > 8 MiB, JSON con claves duplicadas, juego de caracteres no UTF-8, números no finitos | Rechazo con motivo; el cuerpo (si ≤ tope) se guarda con `parse_status = rejected` | Contrato del adaptador | TS-RAW-01…10 |

**Regla de esta tabla:** una amenaza no se da por cubierta porque exista una prueba con nombre parecido; cada prueba debe ejecutar el procedimiento de la columna 4 y comprobar el resultado de la columna 5.

## 4. Licencias y datos sintéticos: una frontera, no un nombre

v2 dependía del prefijo `zz-test-` (V3-11). v3 usa tres capas independientes; cualquiera de ellas basta para impedir que una licencia sintética autorice un mercado real.

| Capa | Mecanismo | Qué impide |
|---|---|---|
| 1. Espacio de nombres | Columna `namespace` (`real` / `synthetic`) en mercados, proveedores y licencias, fijada al crear y no modificable (inmutable). Claves foráneas compuestas (`id`, `namespace`) obligan a que licencia, proveedor y mercado tengan el mismo espacio | Combinar sintético con real, se llame como se llame |
| 2. Rol | Solo `mr.register_synthetic_market/provider/license()` crea filas `synthetic`; solo `mr_test_fixtures` puede ejecutarlas; las funciones de registro de entidades reales rechazan `synthetic` | Crear sintéticos desde la aplicación |
| 3. Instancia | `mr.instance(kind)` se fija en la primera migración (`test` o `production`), no se puede cambiar (disparador y sin privilegios). Si `kind = 'production'`, las funciones sintéticas fallan y una restricción rechaza cualquier fila `synthetic`. El rol `mr_test_fixtures` solo se crea en bases de prueba | Que datos sintéticos existan en una base real, aunque alguien tenga el rol |

En I-1 solo existen bases `test`. La instancia `production` se definirá en I-2 con su propio procedimiento y autorización. Las lecturas de producto (I-2+) filtran `namespace = 'real'` en las funciones `_asof`.

Riesgo residual: un `mr_owner` puede saltarse las tres capas; queda la detección por cadena de hashes y el hecho de que `mr_migrator` no vive en el entorno de la aplicación.

## 5. Conexión y red

**Por qué la guardia de v2 no basta (EXP 18-nov, libpq 16):** `host=localhost hostaddr=192.0.2.1` conecta a 192.0.2.1; un DSN sin host con `PGHOSTADDR` en el entorno también; `host=localhost,192.0.2.1` prueba ambos. Además, `localhost` lo resuelve el sistema (`/etc/hosts`, DNS) y 127.0.0.0/8 tiene más direcciones que 127.0.0.1. (INF) El bloqueo del módulo `socket` de Python no afecta a libpq, que abre sus sockets en C.

**Diseño v3:**

1. **Solo socket Unix en I-1.** No se admite TCP, ni siquiera loopback: el PostgreSQL de pruebas escucha solo en un directorio de sockets (`listen_addresses = ''`).
2. **Conexión construida, no analizada.** `storage/connect.py` recibe parámetros estructurados (`socket_dir`, `dbname`, `user`) y construye la conexión con `host=<ruta absoluta>`; rechaza cualquier entrada que traiga `hostaddr`, `service`, `servicefile`, `passfile`, varios hosts o un `host` que no empiece por `/`.
3. **Entorno limpio.** Antes de conectar, el proceso de I-1 elimina de su entorno todas las variables `PG*` y no lee archivos de servicio (`PGSERVICEFILE` apuntando a `/dev/null`).
4. **Comprobación tras conectar.** `SELECT inet_server_addr()` debe ser NULL (socket Unix) y `mr.instance.kind` debe ser `test`; si no, se cierra la conexión y se aborta. (Nota: para entonces la autenticación ya ocurrió; por eso los pasos 1–3 son los que impiden la conexión y este es una verificación.)
5. **Prueba de red real, a nivel de sistema.** La suite se ejecuta dentro de un espacio de red sin interfaces salvo loopback (`unshare --net` en Linux o contenedor con `--network none`), con el socket Unix montado. Una prueba de control dentro de ese entorno intenta conectar a 192.0.2.1 y a un nombre público, y debe fallar con «red inalcanzable» o resolución fallida. Esto demuestra ausencia de red para **todo** el proceso, incluido libpq.
6. **Falsos positivos:** el bloqueo de red puede impedir que Python resuelva nombres que las pruebas no necesitan; ninguna prueba de I-1 debe necesitar red. Si alguna falla por eso, la prueba está mal diseñada.

## 6. Secretos

I-1 no tiene secretos: bases locales con autenticación `peer` o `trust` sobre socket Unix en un directorio privado. La búsqueda automática de la PR (`I1_ACCEPTANCE_V3.md`) rechaza patrones de clave, `postgres://` con host, `neon.tech` y `render.com`.

## 7. Amenazas que quedan abiertas

| Amenaza | Por qué queda abierta |
|---|---|
| Administrador de base o del host | Puede todo; solo detección |
| Errores en las funciones `SECURITY DEFINER` | Son código privilegiado: revisión obligatoria línea a línea y pruebas adversariales; no hay prueba que demuestre ausencia total de errores |
| Contratos de licencia reales | Ver `I1_LICENSE_ENFORCEMENT.md` §4 |
| Cadena de suministro de `psycopg` y PostgreSQL | Versiones fijadas; fuera del alcance de I-1 |
