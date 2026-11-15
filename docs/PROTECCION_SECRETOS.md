# Protección de secretos (R-08, R-09) · Crypto Radar 2.1.0

Fecha: 2026-11-15. Rama `claude/cierre-riesgos`. Sin desplegar. Ninguna credencial real se ha creado ni cambiado.

## 1. Inventario de claves

| Variable | Para qué | Dónde vive | Si se pierde |
| --- | --- | --- | --- |
| `CRYPTO_RADAR_TOTP_KEY` | Cifra las semillas TOTP en PostgreSQL | Solo en Render (*sync: false*) y en un gestor de contraseñas | Las semillas no se pueden leer. Los usuarios con TOTP vuelven a inscribirlo (§4) |
| `CRYPTO_RADAR_TOTP_KEY_OLD` | Solo durante una rotación: descifra lo cifrado con la clave anterior | Render, unas horas | Nada, si la rotación terminó |
| `CRYPTO_RADAR_BACKUP_KEY` | Firma HMAC-SHA256 de las copias. Obligatoria para crear, verificar, comparar y restaurar | La máquina que hace las copias y el gestor de contraseñas. **No** hace falta en Render | Las copias firmadas con ella ya no se pueden verificar ni restaurar con esta herramienta (§5) |
| `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` | Código de un solo uso para el primer TOTP del administrador | Render, solo hasta usarlo | Se genera otro (`BOOTSTRAP_ADMIN.md`) |

Reglas, comprobadas por `python main.py preflight`:
- Cada clave tiene 32 caracteres o más.
- La clave TOTP y la de copias son **distintas**. Si coinciden, preflight da fallo.
- En Render el servidor **no arranca** sin `CRYPTO_RADAR_TOTP_KEY`. Fuera de Render, igual con
  `CRYPTO_RADAR_TOTP_KEY_REQUIRED=1`.
- Las claves no se escriben en `render.yaml`, en el repositorio ni en el registro. El registro solo muestra el id de
  clave: 8 caracteres hexadecimales de un SHA-256, del que no se puede recuperar la clave.

Para generar una clave, en tu ordenador: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`. Da 43
caracteres.

## 2. Cifrado de las semillas TOTP (R-08)

Está en `radar/secretbox.py` y usa solo la librería estándar. La librería `cryptography` no está entre las
dependencias del servicio, y añadir una dependencia nativa al despliegue era un riesgo nuevo.

La construcción es *encrypt-then-MAC*:
- **Subclaves.** De la clave maestra se derivan dos subclaves independientes con HMAC-SHA256, una para cifrar y otra
  para autenticar.
- **Nonce.** 16 bytes aleatorios en cada cifrado.
- **Cifrado.** Un flujo HMAC-SHA256(k_enc, nonce ‖ contador): una función pseudoaleatoria en modo contador.
- **Etiqueta.** HMAC-SHA256(k_mac, versión ‖ id de clave ‖ **id del usuario** ‖ nonce ‖ cifrado), comparada en tiempo
  constante.
- **Contexto.** Como la etiqueta incluye el id del usuario, el secreto cifrado de una fila no sirve si se copia a otra
  (prueba `T29…ciphertext_bound_to_user`).
- **Formato.** `enc1:<id de clave>:<base64url>`.

Comportamiento:
- **Al arrancar.** Cifra las semillas que estén en claro y recifra con la clave actual las que usen la clave antigua.
  El registro dice cuántas: `Secretos TOTP: X cifrados ahora, Y con la clave nueva`.
- **Clave errónea.** El inicio de sesión con TOTP responde **503**, no cuenta como intento fallido y no bloquea la
  cuenta. El arranque escribe un ERROR. El servidor sigue sirviendo a los usuarios sin TOTP.
- **Sin clave en producción.** No se guarda ninguna semilla nueva en claro (503).
- **Órdenes.** `python main.py secrets status` cuenta las semillas con la clave actual, con la antigua, en claro e
  ilegibles. Termina con código 1 si hay alguna en claro o ilegible. `python main.py secrets encrypt` hace el cifrado
  y la rotación sin reiniciar.
- **`preflight --db`.** Falla si queda alguna semilla en claro o ilegible.
- **Copias.** Las semillas viajan cifradas. La clave TOTP **no** viaja en la copia, así que una copia robada no da los
  segundos factores (prueba `T29…backups_need_key_and_hold_no_plain_totp`).

## 3. Copias con HMAC obligatorio (R-09)

- Ya no existe el modo «sin clave». `backup create`, `verify`, `compare` y `restore` terminan con error si falta
  `CRYPTO_RADAR_BACKUP_KEY` o si es corta. Así no se puede producir una copia que diga «verificada» sin que nadie
  haya podido autenticarla.
- `verify` y `restore` rechazan:
  - una copia sin firma;
  - una copia firmada con otra clave;
  - una copia con el manifiesto o las filas alteradas, aunque se hayan recalculado los SHA-256.
- La firma cubre el manifiesto entero, que incluye el SHA-256 de cada tabla.
- Pruebas: `tests/piloto/ataque_backup.py`, que responde «SIN CLAVE» y no crea nada cuando falta la clave, y
  `tests/piloto/backup_inicial.py`, que cubre la creación sin clave y la verificación con clave errónea.

La copia va **firmada pero no cifrada**: contiene correos y actividad, que son datos personales. Hay que guardarla en
un almacenamiento cifrado y fuera del repositorio. Esto es una recomendación, no un control: la herramienta no puede
obligar a cumplirla.

## 4. Rotación de `CRYPTO_RADAR_TOTP_KEY`

1. Genera una clave nueva y guárdala en el gestor de contraseñas.
2. En Render, mueve el valor actual a `CRYPTO_RADAR_TOTP_KEY_OLD` y pon el nuevo en `CRYPTO_RADAR_TOTP_KEY`.
   Redespliega.
3. En el registro debe aparecer `Secretos TOTP: 0 cifrados ahora, N con la clave nueva`. Comprueba con
   `python main.py secrets status`: todo debe estar con la clave actual, nada con la antigua, nada en claro y nada
   ilegible.
4. Borra `CRYPTO_RADAR_TOTP_KEY_OLD` y redespliega.
5. Haz una copia nueva. Las copias anteriores contienen semillas cifradas con la clave antigua: guarda esa clave junto
   a ellas mientras existan.

Si se usa una clave equivocada (sin `_OLD`), no se pierde nada. Las semillas siguen en la base sin tocar: la
actualización es condicional y nunca sobrescribe lo que no puede descifrar. Basta con volver a poner la clave
correcta. Prueba: `bootstrap_admin.py`, pasos 16 y 17.

**Clave perdida de verdad:** sin ella no hay forma de leer las semillas.
1. Define una clave nueva.
2. Para el administrador, usa `CRYPTO_RADAR_ADMIN_RESET=1` y un código de alta nuevo.
3. Para cada usuario con TOTP, el administrador le restablece la contraseña desde el panel. Esa acción también borra
   el TOTP y cierra sus sesiones. Después, el usuario lo vuelve a inscribir.
4. Las semillas antiguas siguen ilegibles en la base hasta ese momento. `secrets status` las cuenta.

## 5. Rotación de `CRYPTO_RADAR_BACKUP_KEY`

1. Genera una clave nueva y úsala para las copias desde ese momento.
2. **Conserva la anterior** en el gestor de contraseñas, junto con la fecha de la última copia que firmó, mientras se
   guarden copias firmadas con ella. Para verificar o restaurar una de esas copias, define la clave antigua solo para
   esa orden: `CRYPTO_RADAR_BACKUP_KEY=<antigua> python main.py backup verify DIR`.
3. Cuando caduquen todas las copias antiguas (política del §5 de `PLAN_BACKUP_RECUPERACION.md`), destruye la clave
   antigua.

Si se filtra la clave de copias, quien la tenga puede falsificar una copia «válida». Rota la clave de inmediato, haz
una copia nueva y deja de fiarte de las copias que estuvieron al alcance de esa persona.

## 6. Evidencia

- `tests/test_suite.py`, clase `T29_CierreRiesgos`: cifrado, ligado al usuario, rotación, clave errónea → 503,
  migración de semillas en claro, sin texto en claro en producción, preflight con claves cortas o repetidas, copias
  sin clave.
- `tests/piloto/bootstrap_admin.py`: semilla cifrada leída directamente de PostgreSQL, clave errónea y rotación con el
  servidor real.
- `tests/piloto/backup_inicial.py`: copia sin clave rechazada, verificación con clave errónea rechazada, y con otra
  clave TOTP la restaurada responde 503.
