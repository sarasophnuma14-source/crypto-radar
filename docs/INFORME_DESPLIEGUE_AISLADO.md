# Informe del despliegue aislado de la 2.1.0

Fecha: 2026-11-16. **Estado: NO EJECUTADO.** No se ha desplegado nada ni se ha tocado el servicio de la 2.0.0. No se
simula ningún resultado.

## Por qué no se ejecutó (reglas de detención de la parte X)

| Regla | Situación verificada |
| --- | --- |
| 1. No poder distinguir la infraestructura de la 2.0.0 de la nueva | Sin acceso a Render: la API responde 401 y no hay conector. No se puede ver qué servicio ni qué variables usa la 2.0.0 |
| 2. Sin permisos reales para crear Neon | La API de Neon responde 401 y no hay conector |
| 3. Sin permiso para pasar GitHub a privado | La integración de GitHub de esta sesión no ofrece el cambio de visibilidad |
| Protección de la 2.0.0 | El servicio de la 2.0.0 se despliega solo desde `main`, según el historial. Fusionar #3 a #8 antes de cambiarlo de rama sobrescribiría producción |

## Qué sí quedó hecho

- **Rama `production-2.0.0`** en `9176b3662386bea1bdc978d287bd2e27a0fcf79f`, el mismo commit que `main` y que
  producción. Verificado con `git ls-remote`.
- **Procedimiento para fijar la 2.0.0 en esa rama** sin interrumpirla, con la advertencia del Blueprint
  (`ESTADO_LANZAMIENTO_2_1.md` §2).
- **Configuración del servicio nuevo** (`CONFIGURACION_RENDER_2_1.md`) y de la base nueva (`CONFIGURACION_NEON_2_1.md`).
- **Ensayo local del rol de privilegios mínimos** sobre una base nueva:
  - el arranque crea las 11 tablas en el esquema `app`;
  - `platform_meta` = `2.1` / `nueva`;
  - hay 1 administrador y 0 registros heredados;
  - la copia se hace con un rol de solo lectura, que no puede escribir.

  Evidencia: `docs/evidencia_piloto/lanzamiento/neon_privilegios_minimos_local.txt`.
- Siguen vigentes la regresión e integración #3 → #8 (309 / 29 / 39 OK en 3.12 y 3.13) y las demás evidencias de
  `docs/evidencia_piloto/preparacion/`.

## Secuencia pendiente y criterios

Empieza cuando el responsable haya:
1. pasado el repositorio a privado;
2. fijado la 2.0.0 en `production-2.0.0`;
3. dado acceso a Render y Neon (conectores o pasos a mano).

| # | Paso | Criterio de aceptación |
| --- | --- | --- |
| 1 | Verificar con la API que el repositorio es privado, y en Render que la 2.0.0 sigue `production-2.0.0` | `private: true`; *Branch* = `production-2.0.0` |
| 2 | Fusionar #3 → #8 con *merge commit* y pasar la regresión sobre `main` | Árbol de `main` = rama de #8; `test_suite`, `test_edge` y `test_paper` en verde; la 2.0.0 **no** se redespliega |
| 3 | Crear Neon 2.1 y sus roles | `CONFIGURACION_NEON_2_1.md` §2–§4 |
| 4 | Crear el servicio de Render 2.1 con Auto-Deploy desactivado | `CONFIGURACION_RENDER_2_1.md` |
| 5 | `preflight` y `preflight --db` con las variables reales | 0 bloqueantes, salvo G-16 (texto legal), que queda documentado |
| 6 | Despliegue único | Registro: cuentas · postgresql · esquema verificado · plataforma nueva · administrador creado |
| 7 | `/healthz`, inicio de sesión, alta del TOTP, borrar el código de alta y redesplegar | `preflight --db`: TOTP activo; código consumido |
| 8 | Persistencia: crear una cuenta de prueba, reiniciar el servicio y comprobar que sigue | Usuarios y actividad iguales antes y después |
| 9 | Primera copia real | `INFORME_BACKUP_REAL.md` |
| 10 | Prueba de 10 usuarios | `INFORME_PRUEBA_10_USUARIOS.md` |

Si falla una condición crítica:
- *Suspend* del servicio 2.1;
- la 2.0.0 no se toca (`PROCEDIMIENTO_ROLLBACK.md`).

**Alcance:** la instancia queda **interna**. No se abre el registro externo ni se declara GO del piloto mientras G-16
siga pendiente.
