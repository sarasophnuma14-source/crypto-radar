# Estado del lanzamiento aislado · Crypto Radar 2.1.0

Fecha: 2026-11-16 (Bogotá: 2026-11-15, noche).

**Nada desplegado, nada fusionado, producción sin tocar.** Este documento registra:
- qué se hizo;
- qué no se pudo hacer por falta de acceso;
- los pasos exactos que quedan, en orden.

## 1. Inventario verificado

| Recurso | Estado verificado | Cómo se verificó |
| --- | --- | --- |
| `main` | `9176b3662386bea1bdc978d287bd2e27a0fcf79f` (2.0.0) | `git ls-remote origin main` |
| **`production-2.0.0`** | **Creada** en `9176b3662386bea1bdc978d287bd2e27a0fcf79f`, el mismo commit que `main`. Su código no se ha modificado | `git ls-remote origin production-2.0.0` |
| PR #3 a #8 | Abiertos, sin fusionar, apilados linealmente: #3 → `main`, #4 → #3, …, #8 → #7 | API de GitHub (`list_pull_requests`) |
| PR #8, cabeza | `9a01841` | ídem |
| Servicio de Render de la 2.0.0 | **No identificado.** Sin acceso: la API de Render responde 401 y no hay conector | `curl api.render.com` → 401 |
| Base de Neon de la 2.0.0 | **No identificada.** Sin acceso: la API de Neon responde 401 y no hay conector | `curl console.neon.tech/api` → 401 |
| Variables actuales de Render | **No inventariadas.** Sin acceso | — |
| Visibilidad del repositorio | **Pública.** La integración de GitHub de esta sesión no permite cambiarla | — |
| Credenciales en el historial | **Ninguna real.** Se revisaron los 50 commits de todas las ramas | Ver §4 |

Según el historial del proyecto, la 2.0.0 corre en un servicio de Render llamado `crypto-radar` que se despliega solo
desde `main`: así ocurrió al fusionar el PR #1. **No se ha comprobado en Render.**

## 2. Proteger la 2.0.0 (lo hace el responsable, sin interrumpir producción)

Objetivo: que el servicio de la 2.0.0 deje de seguir `main` **antes** de fusionar nada. Así una fusión en `main` nunca
llega a producción.

1. Render → servicio de la 2.0.0 (hoy `crypto-radar`) → **Settings → Build & Deploy**.
2. Anota el valor actual de **Branch** (debería ser `main`) y de **Auto-Deploy**.
3. En **Branch**, elige `production-2.0.0` y guarda.
   - `production-2.0.0` es el mismo commit que está desplegado.
   - [VALIDAR EN REAL] Si Render lanza un despliegue al cambiar de rama, desplegará el **mismo código**. El servicio
     sigue respondiendo durante el despliegue: Render solo cambia de instancia cuando la nueva pasa `/healthz`.
     Para evitar incluso eso, pon antes **Auto-Deploy: Off**.
4. **Si el servicio se creó desde un Blueprint** (Render → *Blueprints*; aparece si `render.yaml` lo gestiona):
   - cambia también la rama del Blueprint a `production-2.0.0`, o desvincúlalo;
   - si no, al sincronizar el Blueprint con `main`, el `render.yaml` de la 2.1 cambiaría las variables del servicio
     de la 2.0.0, por ejemplo `CRYPTO_RADAR_ADMIN_TOTP`, `CRYPTO_RADAR_PAYMENTS` y `MALLOC_ARENA_MAX`.
5. Comprueba:
   - **Events** muestra el cambio de rama y ningún despliegue con un commit distinto de `9176b36`;
   - `GET /healthz` responde 200;
   - la cabecera `Server` dice `CryptoRadar/2.0.0`.
6. Avisa en el hilo. Solo entonces se fusionan los PR (§5).

**No hagas en ese servicio nada más:** ni variables, ni plan, ni base.

## 3. Lo que se preparó para la 2.1.0

- `docs/CONFIGURACION_RENDER_2_1.md`: el servicio **nuevo** e independiente, con plan Starter, región Frankfurt y
  variables nuevas.
- `docs/CONFIGURACION_NEON_2_1.md`: el proyecto Neon **nuevo**, con un rol de aplicación de privilegios mínimos, TLS
  obligatorio y endpoint directo.
- Procedimientos que ya existen y siguen vigentes:
  - `PROCEDIMIENTO_LANZAMIENTO_PILOTO.md` §3 a §8: preflight, bootstrap, humo y prueba de 10 usuarios;
  - `PROCEDIMIENTO_ROLLBACK.md`;
  - `PLAN_BACKUP_RECUPERACION.md`.

## 4. Revisión de secretos en el historial

Patrones buscados en todas las ramas y en todo el historial:
- URL de PostgreSQL con contraseña;
- llaves `pub_prod_` y `prv_prod_` de Wompi;
- tokens de Telegram (`123456789:AA…`), `ghp_`, `AKIA`, claves privadas PEM y contraseñas `npg_` de Neon;
- archivos `.env`, `.pem`, `.key` y `.db`.

Resultado: solo aparecen **valores ficticios** de las pruebas (`ep-x.neon.tech`, `SECRETO_DB`, `pub_prod_abc`) y de
la documentación. No hay ningún archivo `.env`, `.pem` ni base de datos. `data/` está en `.gitignore`.

**Esto no sustituye a pasar el repositorio a privado** (D-4): el código y los procedimientos de seguridad siguen
siendo públicos.

## 5. Orden de lo que queda

| # | Paso | Quién | Estado |
| --- | --- | --- | --- |
| 1 | Pasar el repositorio a privado: GitHub → *Settings* → *General* → *Danger Zone* → *Change visibility* | Responsable (esta sesión no tiene ese permiso) | PENDIENTE |
| 2 | Proteger la 2.0.0 (§2) | Responsable | PENDIENTE |
| 3 | Conectar Render y Neon a Claude, o hacer los pasos a mano | Responsable | PENDIENTE |
| 4 | Fusionar #3 → #8 con *merge commit* y pasar la regresión sobre `main` | Claude, tras los pasos 1 y 2 y tu confirmación | PENDIENTE |
| 5 | Crear Neon 2.1 (`CONFIGURACION_NEON_2_1.md`) | Responsable, o Claude con el conector | PENDIENTE |
| 6 | Crear el servicio de Render 2.1 (`CONFIGURACION_RENDER_2_1.md`) | ídem | PENDIENTE |
| 7 | Preflight, despliegue único, bootstrap del TOTP, persistencia y reinicio, primera copia, prueba de 10 usuarios | ídem | PENDIENTE |
| 8 | G-16: texto legal | Responsable y abogado | **Pospuesto.** Sin él, **no hay GO**: solo una instancia interna restringida |

Mientras no se cumplan los pasos 1 a 3, esta sesión **no** fusiona ni despliega, por las reglas de detención 1 a 3.
