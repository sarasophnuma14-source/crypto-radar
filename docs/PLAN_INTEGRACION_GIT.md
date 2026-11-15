# Plan de integración Git (R-17) · Crypto Radar 2.1.0

Fecha: 2026-11-15. **No se ha fusionado ningún PR ni se ha hecho push a `main`.** Todo lo de este documento se
ejecutó en una rama local desechable (`integracion-local`) dentro de un *worktree* temporal, borrado al terminar.

## 1. Estado de los PR

Todos los PR están abiertos y sin fusionar. Ninguno tiene comprobaciones de CI configuradas en GitHub. #3 tiene
`mergeable_state: clean` según la API de GitHub.

| Orden | PR | Rama | Commit probado | Base | Contenido |
| --- | --- | --- | --- | --- | --- |
| 1 | #3 | `claude/project-thread-i8udp5` | `2d72a2b` | `main` (`9176b36`, 2.0.0, en producción) | Sitio unificado, cuentas aprobadas por el administrador, bootstrap seguro del administrador |
| 2 | #4 | `claude/auditoria-produccion` | `8476715` | #3 | Auditoría de producción, PostgreSQL y Neon, copias, preflight |
| 3 | #5 | `claude/auditoria-final-piloto` | `fedb3a1` | #4 | Auditoría final del piloto |
| 4 | #6 | `claude/estres-integral` | `f79b24c` | #5 | Estrés integral, límites por intentos fallidos, reconexión |
| 5 | #7 | `claude/cierre-riesgos` | ver el PR | #6 | Este cierre de riesgos (R-02, R-08, R-09, R-10) |

**Dependencias.** Cada rama contiene entera a la anterior: el apilado es lineal y #3 parte del `main` actual. Así que
cada PR **depende** de todos los que están debajo. Ninguno se puede fusionar antes que el anterior sin arrastrar el
código de los de abajo.

## 2. Simulación ejecutada

Script: `tests/piloto/integracion_local.sh`. Evidencia: `docs/evidencia_piloto/cierre/integracion_local.txt`.

El script:
1. Crea una rama local desde `origin/main`.
2. Fusiona cada PR en orden con `git merge --no-ff`.
3. Después de cada fusión:
   - comprueba que no haya conflictos;
   - comprueba que el árbol resultante sea **idéntico** al de la rama del PR;
   - ejecuta la regresión completa (`test_suite` contra PostgreSQL 16 real, `test_edge` y `test_paper`) con
     Python 3.12 y 3.13.

| Paso | Conflictos | Árbol = rama | `test_suite` 3.12 / 3.13 | `test_edge` | `test_paper` |
| --- | --- | --- | --- | --- | --- |
| 0 · `main` (2.0.0) | — | — | 158 OK / 158 OK | 29 OK | 39 OK |
| 1 · + #3 | 0 | Sí | 192 OK / 192 OK | 29 OK | 39 OK |
| 2 · + #4 | 0 | Sí | 231 OK / 231 OK | 29 OK | 39 OK |
| 3 · + #5 | 0 | Sí | 258 OK / 258 OK | 29 OK | 39 OK |
| 4 · + #6 | 0 | Sí | 275 OK / 275 OK | 29 OK | 39 OK |
| 5 · + #7 | 0 | Sí | **291 OK / 291 OK** | 29 OK | 39 OK |

Comprobaciones adicionales:
- **Código protegido sin cambios.** `git diff origin/main HEAD -- research radar/quant radar/edge radar/paper_trading`
  sale vacío. La estrategia, el paper trading y el ledger no cambian en ningún paso.
- **Contraprueba con *squash*.** Si se fusiona #3 con «Squash and merge» y después #4 sin rebasar, aparecen
  **conflictos en 14 archivos**, entre ellos `radar/auth.py`, `radar/db.py`, `radar/server.py`, `radar/webapi.py` y
  `render.yaml`. El *squash* reescribe la historia sobre la que se apoyan los PR superiores.

## 3. Secuencia de integración segura (para cuando el responsable la autorice)

**Regla:** usar siempre **«Create a merge commit»**. Nada de *squash* ni *rebase*, porque cualquiera de los dos rompe
el apilado (§2).

1. **Antes de nada:**
   - Haz una copia firmada de la base real (`PLAN_BACKUP_RECUPERACION.md` §1). Hoy la 2.0.0 casi no tiene datos,
     pero la copia deja un punto de vuelta.
   - Haz una consulta de solo lectura `SELECT id, email, status FROM users` para conocer R-22.
   - Prepara las variables nuevas en Render sin desplegar: `CRYPTO_RADAR_TOTP_KEY`, `MALLOC_ARENA_MAX=2`, las del
     administrador y `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN`.
   - **Desactiva el despliegue automático** de Render mientras dure la integración. Si no, cada fusión intermedia en
     `main` dispararía un despliegue.
2. Fusiona **#3 → `main`**. GitHub cambia solo la base de #4 a `main`. Comprueba que #4 muestre únicamente sus propios
   cambios.
3. Fusiona **#4**, luego **#5**, luego **#6** y luego **#7**, siempre con *merge commit*. Tras cada uno, la base del
   siguiente pasa a `main`.
4. Comprueba que `main` tenga exactamente el árbol de `claude/cierre-riesgos`:
   `git diff origin/main origin/claude/cierre-riesgos` debe salir vacío. Ejecuta en `main`
   `tests/piloto/integracion_local.sh` o, como mínimo, los tres archivos de pruebas.
5. Ejecuta `python main.py preflight --db` con las variables reales. Debe dar 0 fallos: hoy falla el texto legal, R-01.
6. Vuelve a activar el despliegue y despliega **una sola vez**, desde el `main` final.
7. Después del despliegue:
   - alta del TOTP del administrador (`BOOTSTRAP_ADMIN.md` §3);
   - borra `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN`;
   - primera copia real;
   - prueba de 10 usuarios (`tests/piloto/prueba_render_10.py`).

**Vuelta atrás.** En Render, «Rollback» al despliegue de la 2.0.0. En Git, `git revert -m 1` de los *merge commits*,
en orden inverso. Ninguna migración borra columnas ni tablas, así que la 2.0.0 sigue funcionando sobre la base
migrada: las columnas nuevas no le afectan. Esto se razonó sobre el código; no se ensayó.

**Alternativa equivalente:** fusionar solo #7 contra `main`, cambiando antes su base a `main`. Incluye todo el apilado
en un único *merge commit* y cierra a mano #3 a #6. Es más simple, pero pierde la revisión PR a PR.

## 4. Qué no se pudo comprobar

- Que GitHub cambie la base de cada PR automáticamente al fusionar el anterior. Es su comportamiento documentado, pero
  aquí no se ejecutó, por la regla de no fusionar.
- No hay CI en GitHub. La regresión es la local de este documento, y conviene repetirla sobre el `main` final.
