# Procedimiento de rollback · Crypto Radar 2.1.0 → 2.0.0

Fecha: 2026-11-15. **Preparado, no ensayado en Render.** Las reglas de esta fase prohíben desplegar. Los pasos de Git y
de base de datos sí están probados en local, como se indica en cada caso.

## 1. Cuándo volver atrás

Se vuelve a la 2.0.0, o se pausa el servicio, si en las primeras 48 h ocurre cualquiera de estas cosas:
- `/healthz` falla durante más de 5 minutos seguidos, o Render reinicia el servicio en bucle;
- aparece una vía de acceso que no debería existir: una cuenta antigua entra, hay dos administradores o un usuario
  normal llega a una ruta de administración;
- hay pérdida o corrupción de datos;
- la prueba de 10 usuarios no se aprueba y no se puede corregir en el día.

Los criterios de suspensión del piloto, que son más amplios, están en `PROCEDIMIENTO_LANZAMIENTO_PILOTO.md` §9.

**Antes de volver atrás, valora pausar.** Desactivar las cuentas desde el panel, o bajar el servicio en Render, suele
bastar y no pierde nada.

## 2. Requisitos que hay que dejar listos ANTES del despliegue

Sin ellos, el rollback no es seguro.

1. **Inventario de variables de la 2.0.0.** Anota cuáles tiene definidas hoy el servicio de Render: solo los
   **nombres** y, aparte, en el gestor de contraseñas, los valores. Según el historial del proyecto, la 2.0.0 corre en
   modo de un solo usuario, sin `CRYPTO_RADAR_ACCOUNTS`.

   **Peligro.** La 2.0.0 con `CRYPTO_RADAR_ACCOUNTS=1` abre el registro libre, y la primera persona que se registre
   con `CRYPTO_RADAR_ADMIN_EMAIL` pasa a ser administradora (código de `origin/main`, `radar/auth.py:register`). Si se
   vuelve a la 2.0.0, hay que **restaurar sus variables**, no dejar las de la 2.1.
2. **Base de la 2.1 separada.** Se recomienda una base nueva y vacía en Neon para la 2.1
   (`CONFIGURACION_RENDER_NEON.md` §3). Así la 2.0.0 y sus datos no se tocan nunca y volver atrás consiste en cambiar
   el código y las variables.
3. **Si se reutiliza la base de la 2.0.0** (no recomendado):
   - crea **antes** una rama de Neon de esa base, que sirve como punto de vuelta;
   - haz además una copia firmada (`PLAN_BACKUP_RECUPERACION.md` §1);
   - el primer arranque de 2.1 archiva las cuentas de la 2.0.0 (`REGISTRO_USUARIOS_PILOTO.md` §1), así que la 2.0.0
     no podría usarlas en esa base.
4. **Deshabilitar el despliegue automático** mientras se fusionan los PR (`PLAN_INTEGRACION_GIT.md` §3).
5. Identificar en Render el **último despliegue de la 2.0.0**: commit `9176b36` en `main`.

## 3. Rollback del servicio (Render)

1. En Render → servicio → *Events* o *Deploys*, haz «Rollback» al despliegue de `9176b36`.

   [VALIDAR EN REAL] Comprueba en ese momento si el rollback de Render conserva las variables de entorno **actuales**:
   no se pudo verificar sin acceso. Si las conserva, el paso 2 es obligatorio.
2. Restaura las variables del inventario del §2.1:
   - borra `CRYPTO_RADAR_ACCOUNTS`, o déjala como estaba en la 2.0.0;
   - pon `DATABASE_URL` como estaba;
   - las variables nuevas de la 2.1 (`CRYPTO_RADAR_TOTP_KEY`, `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN`, `CRYPTO_RADAR_PILOT`)
     no afectan a la 2.0.0, pero quítalas para no dejar secretos sin uso.
3. Comprueba:
   - `/healthz` responde 200 y la cabecera `Server` dice `CryptoRadar/2.0.0`;
   - el panel de un solo usuario pide la contraseña de siempre;
   - **no** está abierta la página de registro de la 2.0.0.
4. La base de la 2.1 queda intacta. Si se vuelve a desplegar la 2.1 más tarde, arranca sobre ella sin cambios: la marca
   de plataforma ya existe.

## 4. Rollback de Git

Solo si ya se fusionaron los PR en `main` y se quiere que `main` vuelva a la 2.0.0:

```bash
git checkout main && git pull
git revert -m 1 <merge de #7> <merge de #6> <merge de #5> <merge de #4> <merge de #3>   # en orden inverso
git diff 9176b36 HEAD --stat        # debe salir vacío
```

Se revierte en vez de reescribir la historia, para no hacer *force-push* a `main`. Probado en local: tras la secuencia
de *merge commits* de `PLAN_INTEGRACION_GIT.md`, el árbol de cada paso coincide con su rama, así que revertir los
*merges* en orden inverso devuelve el árbol de `9176b36`.

## 5. Rollback de datos

| Escenario | Acción | Pérdida |
| --- | --- | --- |
| La 2.1 usó una base nueva | Nada que restaurar: la 2.0.0 nunca la tocó | Ninguna en la 2.0.0. Lo escrito en la 2.1 se conserva para un nuevo intento |
| La 2.1 reutilizó la base de la 2.0.0 | Apuntar la 2.0.0 a la **rama de Neon** creada antes del despliegue, o restaurar la copia previa en una base vacía (`main.py backup restore … --target`) | Lo escrito en la 2.0.0 después de la copia (RPO) |
| Corrupción dentro de la 2.1 | `RECUPERACION_DESASTRES.md` §3 (rama de Neon o copia propia) | Desde la última copia |

`backup restore` solo restaura en una base **vacía** y se niega a usar la de `DATABASE_URL`. Con un corte a mitad, la
base queda vacía porque todo va en una transacción, y se puede repetir. Probado: `T31_CopiasExtremos`, con SIGKILL
real en PostgreSQL.

## 6. Después del rollback

- Avisa a los usuarios del piloto de que el servicio está pausado. No hace falta pedirles nada: sus cuentas de la 2.1
  siguen en la base de la 2.1.
- Registra la causa en `docs/MATRIZ_RIESGOS_PENDIENTES.md` y no vuelvas a desplegar sin una prueba que reproduzca el
  fallo.
