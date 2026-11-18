# Respaldos independientes: diseño, recuperación de claves y simulacros

Auditoría correctiva, hallazgo H5 (2026-11-16). Sustituye a la recomendación anterior («GitHub Actions + age»), que el
propietario rechazó con razón: si la copia, su programación y su almacenamiento dependen de la misma cuenta que el
repositorio, un solo incidente (cuenta comprometida, suspendida o borrada) se lleva el código **y** las copias.

**Estado: TODO DESACTIVADO.** El código existe y está probado; no hay cron, workflow ni servicio que lo ejecute, no se
creó ningún almacenamiento ni ninguna clave, y ninguna orden hace nada sin `CRYPTO_RADAR_BACKUP_JOB=1`. Costos de los
proveedores: **sin cotizar**.

## 1. Principios

1. **Tres dominios de fallo separados.** Base (Neon), aplicación y código (Render, GitHub) y copias (un proveedor de
   almacenamiento distinto, en una cuenta propia del propietario con MFA). Ninguna credencial de uno sirve en otro.
2. **Quien copia no puede leer ni borrar.** La máquina que hace la copia solo tiene claves age **públicas** y una clave
   de almacenamiento de **solo escritura**. Comprometerla no expone copias anteriores ni permite borrarlas.
3. **Nada se da por bueno sin restaurarlo.** Cada copia se verifica al crearla (firma, hashes, restauración en SQLite) y
   periódicamente se restaura de verdad en una base PostgreSQL vacía.
4. **El silencio también es una alerta.** El aviso no depende de que el job llegue a ejecutarse: un servicio de latidos
   externo avisa si no recibe el «ok» en el plazo.

## 2. Cadena de la copia (`python main.py offsite job`)

| Paso | Qué hace | Falla si… |
|---|---|---|
| 1. Copia lógica | `backup.create`: todas las tablas en una transacción `REPEATABLE READ` de solo lectura, firmada con HMAC (`CRYPTO_RADAR_BACKUP_KEY`) | no hay clave, la base no responde |
| 2. Verificación | `backup.verify`: firma + SHA-256 por tabla + restauración real en SQLite temporal | la copia no se puede restaurar |
| 3. Cifrado | `tar` → `age` con **dos destinatarios públicos** (propietario + custodia) | falta `age` o un destinatario no es una clave pública `age1…` |
| 4. Subida | objeto `crypto-radar/crypto-radar-AAAAMMDD-HHMMSS.tar.age` + sidecar `.json` firmado (tamaño, SHA-256, filas por tabla; **sin datos personales**) | el destino rechaza la escritura |
| 5. Relectura | descarga lo subido y compara el SHA-256 | lo almacenado no coincide |
| 6. Latido | `GET CRYPTO_RADAR_BACKUP_HEARTBEAT_URL` si todo fue bien; `…/fail` con una línea de motivo (sin URL ni datos) si no | — |

Destinos soportados: `CRYPTO_RADAR_BACKUP_DEST=s3` (cualquier S3 compatible por HTTPS, firma SigV4 implementada con la
biblioteca estándar y comprobada con los ejemplos publicados por AWS) o `dir:/ruta` (disco externo o NAS).

## 3. Retención

Recomendación (el plazo final es del propietario y debe ser coherente con la política de privacidad, G-16): **14 diarias,
8 semanales, 12 mensuales**, y la más reciente siempre.

Cómo se aplica, por orden de preferencia:

1. **En el proveedor:** bloqueo de objetos (*Object Lock*, modo cumplimiento) durante el periodo mínimo y regla de ciclo
   de vida que borre después. La clave del job no puede borrar ni acortar el bloqueo.
2. **Poda manual** con `python main.py offsite prune` (simula) y `--apply` (borra), que exige además
   `CRYPTO_RADAR_BACKUP_PRUNE=1` y debe usar **otra** clave con permiso de borrado, en manos del propietario.

## 4. Claves y su recuperación

| Clave | Para qué | Dónde vive | Si se pierde |
|---|---|---|---|
| Identidad age del **propietario** (privada) | descifrar copias | gestor de contraseñas del propietario **y** copia impresa en sobre cerrado | se usa la de custodia |
| Identidad age de **custodia** (privada) | descifrar copias si falta la anterior | persona o lugar de confianza distinto (segunda caja, notaría, socio) | se usa la del propietario; generar otra y rotar destinatarios |
| Claves públicas `age1…` de ambas | cifrar | en la máquina que copia | se regeneran desde las privadas (`age-keygen -y`) |
| `CRYPTO_RADAR_BACKUP_KEY` | firma HMAC de copias y sidecars | gestor de contraseñas + junto a cada identidad privada | sin ella no se puede **verificar** (sí descifrar): guardarla con las identidades |
| `CRYPTO_RADAR_TOTP_KEY` | leer los segundos factores restaurados | gestor de contraseñas, aparte | los administradores tendrán que volver a dar de alta su TOTP |
| Clave S3 de **solo escritura** | subir | máquina que copia | se revoca y se crea otra; no da acceso a lo ya subido |
| Clave S3 de **lectura** | simulacros | máquina del simulacro | se revoca y se crea otra |

Procedimiento de generación (lo hace el propietario, sin conexión, nunca en un chat):

```bash
age-keygen -o propietario.txt     # imprime la clave pública; la privada queda en el archivo
age-keygen -o custodia.txt
# guardar cada archivo como se indica arriba y borrar las copias locales
```

**Prueba de recuperación de claves:** el simulacro mensual alterna la identidad: meses impares con la del propietario,
pares con la de custodia. Así se comprueba que ambas siguen existiendo y funcionan (prueba automática:
`test_2_recuperacion_con_la_segunda_clave_y_rechazo_de_una_ajena`).

## 5. Simulacro de restauración (`python main.py offsite drill`)

```bash
python main.py offsite drill --target 'postgresql://…/base_vacia_de_prueba' --identity propietario.txt
```

Descarga la última copia, comprueba la firma del sidecar y el SHA-256, descifra, verifica, restaura en una base **vacía**
(se niega con la base de producción o con una base con datos), compara tabla a tabla y emite su propio latido. Si la
copia tiene más de `CRYPTO_RADAR_BACKUP_MAX_AGE_H` horas (26 por defecto) lo trata como alerta.

Frecuencia recomendada: **mensual**, en una rama vacía de Neon o en un PostgreSQL 16 local, que se borra al terminar.
Cada simulacro deja una línea en el registro de simulacros (fecha, objeto, filas, duración, resultado).

## 6. Dónde se ejecuta

Requisito: **fuera** de Render y de GitHub. Opciones, sin cotizar:

| Opción | Ventaja | Inconveniente |
|---|---|---|
| Ordenador o mini servidor del propietario con `cron` (plantilla en `docs/plantillas/respaldo-externo.cron`) | sin proveedor nuevo; control total | depende de que esté encendido (el latido lo detecta) |
| Máquina virtual pequeña en un proveedor distinto | siempre encendida | proveedor y costo nuevos |
| Render Cron Job | ya se usa Render | **no recomendado**: mismo dominio de fallo que la app |
| GitHub Actions | gratis | **no recomendado** como único medio (motivo de este hallazgo) |

## 7. Alertas

`CRYPTO_RADAR_BACKUP_HEARTBEAT_URL` y `CRYPTO_RADAR_BACKUP_DRILL_HEARTBEAT_URL` apuntan a un servicio de latidos
(*dead man's switch*) de un proveedor externo, configurado para avisar al propietario por correo y otro canal si:
llega `/fail`, o no llega nada en 26 h (copia) o en 35 días (simulacro). El aviso nunca contiene datos de la base.

## 8. Procedimiento de recuperación (resumen; el detalle de incidentes sigue en `RECUPERACION_DESASTRES.md` §3)

1. Crear una base nueva y vacía en Neon (o en otro PostgreSQL 16).
2. En una máquina de confianza: `offsite drill --target <base nueva> --identity <propietario o custodia>`. Debe terminar
   con `"ok": true`.
3. Cambiar `DATABASE_URL` del servicio a la base nueva (**acción del propietario**) y redesplegar.
4. Comprobar `/healthz`, entrar como administrador con TOTP (requiere la misma `CRYPTO_RADAR_TOTP_KEY`).
5. Reconciliar lo escrito después de la copia (RPO ≤ 24 h con copia diaria).

## 9. Pruebas (tests/test_respaldo_externo.py)

12 pruebas; con `TEST_DATABASE_URL` el origen y los destinos del simulacro son bases PostgreSQL 16 reales creadas y
borradas por la prueba. Cubren: desactivado por defecto; ninguna programación activa en el repositorio; rechazo de
claves privadas como destinatario; firma SigV4 contra dos ejemplos publicados por AWS y contra un S3 simulado que
comprueba cada firma; copia cifrada sin datos en claro en el destino; simulacro en base vacía; recuperación con la
clave de custodia; rechazo de una clave ajena; alteración del objeto y del sidecar detectadas; fallo de la base con
aviso sin filtrar la URL; negativa a restaurar sobre producción o sobre una base con datos; copia vieja como alerta;
retención diaria/semanal/mensual; poda que por defecto solo simula.

## 10. Pendiente del propietario

1. Elegir proveedor de almacenamiento y de latidos (cuenta propia con MFA) y aceptar su costo (sin cotizar).
2. Activar bloqueo de objetos y ciclo de vida, y crear las claves de solo escritura, lectura y borrado.
3. Generar las dos identidades age y decidir quién custodia la segunda.
4. Elegir la máquina que ejecuta la copia (fuera de Render y GitHub).
5. Usar para la copia un rol de **solo lectura** de Neon (no el rol de la aplicación).
6. Hacer el primer simulacro manual y, si sale bien, autorizar la activación (`CRYPTO_RADAR_BACKUP_JOB=1`).
