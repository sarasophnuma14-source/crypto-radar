# Alta segura del administrador (R-02) · Crypto Radar 2.1.0

Fecha: 2026-11-15. Rama `claude/cierre-riesgos` (PR apilado sobre #6, sin fusionar, sin desplegar).

## 1. El problema

Antes, el primer segundo factor (TOTP) del administrador se inscribía por «confianza en el primer uso». Quien conociera
la contraseña del administrador antes de que este activara su TOTP podía entrar e inscribir **su propio** teléfono.
Desde ese momento el atacante tenía los dos factores y el administrador legítimo quedaba fuera.

## 2. El mecanismo: código de alta de un solo uso

Para inscribir o volver a inscribir el TOTP de **cualquier cuenta de administrador** hace falta, además de la contraseña,
un **código de alta**. Ese código solo lo tiene quien controla el servidor: la línea de órdenes o las variables de
entorno de Render. La contraseña sola ya no basta.

| Propiedad | Cómo se consigue |
| --- | --- |
| Secreto fuerte | 32 bytes aleatorios (`secrets.token_urlsafe(32)`); el del entorno debe tener 32 caracteres o más |
| No se guarda en claro | En la tabla `admin_enroll_tokens` solo queda `sha256("crypto-radar/enroll|" + código)` |
| Caduca | Desde la línea de órdenes: 30 min (ajustable). Desde el entorno: 24 h desde el primer arranque que lo registra |
| Un solo uso | Se consume dentro de la misma operación que activa el TOTP: `UPDATE … SET used_at = … WHERE token_hash = ? AND used_at IS NULL` |
| Sin repetición | Un código consumido no vuelve a valer, ni tras reiniciar ni tras restaurar una copia (la tabla va en la copia) |
| Concurrencia | Si dos peticiones usan el mismo código a la vez, solo una gana. La otra recibe 409 y su TOTP no queda activado |
| Fuerza bruta | 10 intentos por administrador cada 15 min (respuesta 429). Un código erróneo **no** bloquea la cuenta ni suma fallos de inicio de sesión |
| Atacante con la contraseña | Puede entrar, pero el panel le pide el código de alta. Sin TOTP no puede administrar (403). Cuando el administrador legítimo activa su TOTP, se cierran todas las sesiones abiertas, también la del atacante |
| Usuarios normales | No cambian: inscriben su TOTP sin código |

El código se pide en dos momentos:
1. `POST /api/auth/totp/setup`, que genera la semilla.
2. `POST /api/auth/totp/enable`, que la confirma y consume el código.

Así, un atacante no puede quedarse con una inscripción a medias para completarla después.

## 3. Procedimiento del primer despliegue

1. En Render, define `CRYPTO_RADAR_TOTP_KEY` (ver `PROTECCION_SECRETOS.md`), `CRYPTO_RADAR_ADMIN_USER`,
   `CRYPTO_RADAR_ADMIN_PASSWORD` y `CRYPTO_RADAR_ADMIN_TOTP=required`.
2. Genera el código **en tu ordenador**, sin escribirlo en ningún archivo:
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
3. Pégalo en Render como `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN`, con *sync: false*. Esa variable no está en `render.yaml`
   a propósito.
4. Despliega. En el registro debe aparecer `Código de alta del administrador: registrado (vale 24 h, un solo uso)`.
5. Entra con usuario y contraseña. En «Seguridad» aparece el campo «Código de alta de administrador». Pega el código,
   escanea el QR y confirma con un código de 6 cifras.
6. **Borra** `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` de Render. Si se queda, no sirve de nada: el registro dice
   `usado (bórralo del entorno)` y `preflight` lo avisa.
7. Comprueba con `python main.py preflight --db`. Debe decir «TOTP del administrador en la base: activo».

**Alternativa sin variable de entorno.** Ejecuta `python main.py admin enroll-token` en la *Shell* de Render, o en
cualquier máquina con la `DATABASE_URL` real. Imprime un código que vale 30 minutos (`admin enroll-token 10` lo deja en
10 minutos). Ese código no queda en el registro del servidor ni en las variables de entorno.

## 4. Recuperación: no se bloquea al administrador legítimo

| Situación | Qué hacer |
| --- | --- |
| Perdí el teléfono (TOTP ya activo) | Define `CRYPTO_RADAR_ADMIN_RESET=1` y redespliega: se restablecen la contraseña del entorno y el TOTP. Genera un código nuevo (`admin enroll-token` o una variable nueva) e inscribe el teléfono nuevo. Quita `CRYPTO_RADAR_ADMIN_RESET` |
| El código caducó o ya se usó | Genera otro con `main.py admin enroll-token`, o pon un valor **nuevo** en la variable. El antiguo nunca revive |
| Me equivoqué al teclearlo | Hasta 10 intentos cada 15 min. Después hay que esperar; la cuenta no se bloquea |
| Clave TOTP del entorno perdida o errónea | El inicio de sesión responde 503 y no cuenta como fallo. Restablece con `CRYPTO_RADAR_ADMIN_RESET=1` y vuelve a inscribir (ver `PROTECCION_SECRETOS.md` §4) |

Todas estas vías exigen controlar el servidor (Render o `DATABASE_URL`). Es la misma barrera que ya protegía la
contraseña del administrador.

## 5. Pruebas (ejecutadas)

**Unitarias, clase `T29_CierreRiesgos` de `tests/test_suite.py`.** 16 casos, entre ellos:
- alta sin código o con un código inventado: rechazada;
- repetición del código: rechazada;
- código caducado: rechazado;
- **6 administradores usando el mismo código a la vez: gana solo uno**;
- un atacante no puede secuestrar una inscripción pendiente;
- el código del entorno sigue usado tras reiniciar;
- límite de intentos sin bloquear la cuenta;
- recuperación tras perder el teléfono;
- los usuarios normales no necesitan código.

**De extremo a extremo, `tests/piloto/bootstrap_admin.py`.** Usa el servidor real (`main.py serve`) sobre un
PostgreSQL temporal. Resultado: **17 de 17 pasos OK**. Evidencia: `docs/evidencia_piloto/cierre/bootstrap_admin.json`.

```
PG_ADMIN_URL=postgresql://radar@127.0.0.1:55432/radar python tests/piloto/bootstrap_admin.py salida.json
```

## 6. Lo que queda fuera

- El código del entorno queda visible para quien tenga acceso al panel de Render. Acceso a Render ya equivale a control
  total del servicio, así que no añade exposición. Con `admin enroll-token` tampoco queda ahí.
- Hace falta comprobar en el despliegue real que el administrador activó su TOTP: pasos 4 a 7 del §3. Es una
  **validación externa**.
