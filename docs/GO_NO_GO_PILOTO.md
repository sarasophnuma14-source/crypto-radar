# GO / NO-GO del piloto cerrado · Crypto Radar 2.1.0

Fecha: 2026-11-15. Rama `claude/preparacion-piloto` (PR #8, apilado sobre #7). Nada desplegado ni fusionado.

**Regla:** el piloto solo puede abrirse (GO) si no queda ningún requisito BLOQUEANTE y todos los PENDIENTES marcados
como «antes de abrir» están cerrados. Un requisito solo es CERRADO si tiene una prueba **ejecutada**; una
recomendación escrita no basta.

## Veredicto: **NO-GO**

> **Actualización 18-nov-2026 (auditoría correctiva, `AUDITORIA_CORRECTIVA_2026-11-16.md`): sigue NO-GO.** Se
> corrigieron 7 hallazgos en las PR #12, #13, #14 y #15, sin fusionar ni desplegar. Requisitos nuevos:
>
> | ID | Descripción | Estado | Evidencia |
> | --- | --- | --- | --- |
> | G-27 | Fencing transaccional del líder (H3) | PENDIENTE: probado en local, falta desplegar la PR #12 | `FencingGeneracion` 7/7 sobre PG16, con reinicio real |
> | G-28 | La app usa el endpoint directo de Neon (H4) | PENDIENTE: confirmación del propietario (R-23) | `preflight` falla con `-pooler` |
> | G-29 | Métricas del piloto con denominadores correctos (H1, H2) | CERRADO en código (PR #14); la instrumentación sigue apagada | `ActivacionH1`, `IntencionDePagoH2` |
> | G-30 | Respaldos independientes con simulacro y alertas (H5) | **BLOQUEANTE**: código listo y desactivado (PR #15); faltan proveedor, claves y el primer simulacro | `test_respaldo_externo` 12/12 |
> | G-31 | Política de privacidad coherente con la instrumentación (H7) | Ligado a G-16 (BLOQUEANTE): falta el plazo de retención y la revisión jurídica | `PrivacidadH7` 8/8 |
>
> Que las pruebas locales pasen **no** cambia el veredicto.

Estado técnico: **PREPARADO PARA PILOTO.** No queda ningún bloqueante técnico:
- el código está corregido y la suite completa se ejecutó;
- la migración no permite acceso heredado;
- el administrador inicial está protegido;
- las copias son verificables;
- la configuración y el rollback están documentados.

Aun así el veredicto es NO-GO, por:
- **1 BLOQUEANTE no técnico (G-16):** el texto legal de privacidad está sin completar y sin revisión jurídica;
- **8 PENDIENTES** que necesitan acceso real o una decisión del responsable (G-17, G-18 y G-20 a G-25).

Estados: **CERRADO** (corregido y probado) · **MITIGADO** (control probado con riesgo residual aceptable) ·
**PENDIENTE** (preparado; falta acceso real, autorización o decisión) · **BLOQUEANTE** (impide abrir el piloto).

## Requisitos

| ID | Descripción | Estado | Evidencia | Responsable | Procedimiento | Criterio de aceptación | Riesgo residual |
| --- | --- | --- | --- | --- | --- | --- | --- |
| G-01 | Plataforma nueva: ninguna cuenta, contraseña, sesión, token, plan ni vínculo de 2.0.0 sirve para entrar; lo histórico queda aparte | CERRADO | `plataforma_nueva.json` 41/41 (SQLite y PostgreSQL); `T30`; `T18…archives_users`; `T17` (PostgreSQL) | Equipo técnico | `REGISTRO_USUARIOS_PILOTO.md` §1 | Antiguo → 401; cookie antigua → 401; plan no heredado; archivo sin credenciales | Si se reutiliza la base de la 2.0.0, su autenticación queda archivada: usar una base nueva (D-2) |
| G-02 | Un único administrador; ninguna vía para crear otro ni para escalar privilegios | CERRADO | `T30…extra_admin…`, `T30…new_users_never_get_admin`; `plataforma_nueva.py` (7 rutas → 403, cambio de administrador) | Equipo técnico | `REGISTRO_USUARIOS_PILOTO.md` §2 | `count(is_admin) = 1` en cada arranque | Quien controle las variables de Render controla el administrador: es inherente |
| G-03 | Alta del TOTP del administrador con código de un solo uso, con hash, caducidad, consumo atómico, concurrencia y recuperación | CERRADO | `T29` (16 casos); `bootstrap_admin.py` 17/17 | Equipo técnico | `BOOTSTRAP_ADMIN.md` | Sin código → 403; repetido → 403; 6 en paralelo → 1 | — |
| G-04 | TOTP obligatorio para administrar; el servidor no arranca con TOTP opcional en Render | CERRADO | `T21`; `T30…insecure_config…` | Equipo técnico | `CONFIGURACION_RENDER_NEON.md` §2 | Sin TOTP → 403 en administración | — |
| G-05 | Semillas TOTP cifradas; claves de cifrado y de copias distintas; rotación documentada | CERRADO | `T29`; `bootstrap_admin.py` (lectura directa en PostgreSQL) | Equipo técnico | `PROTECCION_SECRETOS.md` | `secrets status`: 0 en claro; claves iguales → no arranca | Perder la clave TOTP obliga a reinscribir el TOTP |
| G-06 | Copias con HMAC obligatorio; rechazo de copias sin clave, con otra clave, manipuladas o incompletas; restauración solo en base vacía, atómica y repetible | CERRADO | `T23`, `T31` (con SIGKILL real en PostgreSQL); `backup_inicial.py` 15/15 en esta rama (el paso con latencia solo corre con `LATENCIA_MS`; 16/16 en #7, también a escala ×5) | Equipo técnico | `PLAN_BACKUP_RECUPERACION.md` | Todos los casos rechazados; restauración interrumpida → base vacía | La copia va firmada, no cifrada: guardarla cifrada es un procedimiento |
| G-07 | El arranque se niega con configuración insegura y no revela secretos | CERRADO | `T30…insecure_config…` (8 casos), `T30…serve_refuses_before_touching_the_database`, `T19` | Equipo técnico | `radar/pilot.py` | Mensaje con el nombre de la variable, nunca su valor | — |
| G-08 | Preflight APROBADO / ADVERTENCIA / BLOQUEANTE, alineado con el arranque | CERRADO | `T24`; `preflight_tipo_render_*.txt` | Equipo técnico | `CONFIGURACION_RENDER_NEON.md` §1 | Entorno inseguro → 8 bloqueantes; correcto → solo G-16 | — |
| G-09 | Pagos imposibles durante el piloto: live → off, sandbox prohibido en Render, sin planes sin autorización, webhooks idempotentes | CERRADO | `T32` (5), `T14`, `T22`, `T26` | Equipo técnico | `CONFIGURACION_RENDER_NEON.md` §6 | Pago o *webhook* → 503; planes sin cambio | Los proveedores nunca se probaron en sandbox real (R-03): solo hace falta al salir del piloto |
| G-10 | Registro con aprobación manual, rechazo, registro de acciones, bloqueo temporal, CSRF, duplicados, enumeración en el inicio de sesión | CERRADO | Pruebas listadas en `REGISTRO_USUARIOS_PILOTO.md` §3–4 | Equipo técnico | ídem | Todas en verde | Al solicitar acceso se revela si un nombre está ocupado (limitado a 3 por IP y hora) |
| G-11 | La interfaz dice que es un piloto cerrado, no simula cobros ni promete rentabilidad | CERRADO | `T32…interface…`, `T32…no_promises…` | Equipo técnico | — | Aviso en `/entrar`, en precios y en la app | — |
| G-12 | Arranque simultáneo de varias instancias sobre PostgreSQL | CERRADO | `plataforma_nueva.py`: 4 procesos, 0 errores (antes, uno caía: F-10) | Equipo técnico | — | 0 errores | — |
| G-13 | Rendimiento local con 1, 5, 10, 20 y 50 usuarios, con escaneo y corte de conexiones | MITIGADO | `carga_1_50_local.json`, `carga_1_50_starter_emulado.json` | Equipo técnico | `INFORME_FINAL_PREPARACION_PILOTO.md` §5 | p95 < 1 s, 0 respuestas 5xx, recuperación tras el corte | Es local: **no** valida Render ni Neon (G-21) |
| G-14 | Integración Git #3 → #8 sin conflictos y regresión completa en cada paso; código protegido sin cambios | CERRADO | `integracion_local_preparacion.txt`: 0 conflictos, árbol idéntico en cada paso, 309 / 29 / 39 OK en 3.12 y 3.13 | Equipo técnico | `PLAN_INTEGRACION_GIT.md` | 0 conflictos; todo en verde; `research/`, `radar/quant/`, `radar/edge/` y `radar/paper_trading/` sin diferencias | Sin CI en GitHub: repetir la regresión sobre el `main` final |
| G-15 | Rollback preparado | MITIGADO | `PROCEDIMIENTO_ROLLBACK.md`; reversión de Git y restauración probadas en local | Responsable | ídem | Inventario de variables guardado (G-24) | No ensayado en Render |
| G-16 | Política de privacidad completa y revisada por un abogado (Ley 1581) | **BLOQUEANTE** | `preflight`: 11 marcas pendientes en `privacidad.html` | Responsable + abogado | `POLITICA_PRIVACIDAD_BORRADOR.md`, lista P-1 a P-7 | `preflight` sin el bloqueante del texto legal; aprobación escrita del abogado | — |
| G-17 | Fusión de los PR #3 a #8 y despliegue | PENDIENTE | — | Responsable (autorización) | `PROCEDIMIENTO_LANZAMIENTO_PILOTO.md` §1, §5 | `main` = rama; registro de arranque correcto | — |
| G-18 | `preflight --db` con las variables reales: 0 bloqueantes | PENDIENTE | — | Responsable | ídem §3 | 0 bloqueantes | — |
| G-19 | Atención de los derechos de los titulares (consulta y supresión) | MITIGADO | Procedimiento manual en `REGISTRO_USUARIOS_PILOTO.md` §6 | Responsable | ídem | Respuesta en plazo | Manual: automatizarlo antes de la fase 3 |
| G-20 | Copia previa de la 2.0.0 y primera copia real de la 2.1 verificadas | PENDIENTE | — | Responsable | `PLAN_BACKUP_RECUPERACION.md` §1 | `backup verify` OK | — |
| G-21 | Prueba de 10 usuarios en Render + Neon | PENDIENTE | Preparada: `prueba_render_10.py` (ensayo local APROBADO) | Responsable (autorización) | Lanzamiento §8 | p95 < 1 s, 0 respuestas 5xx, 0 > 2 s, 0 respuestas 429, los 10 entran | — |
| G-22 | TOTP del administrador activo en producción y código de alta borrado | PENDIENTE | — | Responsable | `BOOTSTRAP_ADMIN.md` §3 | `preflight --db`: «activo» | — |
| G-23 | Historial de Neon y restauración por rama verificados | PENDIENTE | — | Responsable | `PLAN_BACKUP_RECUPERACION.md` §6 | Ventana conocida | — |
| G-24 | Decisiones previas D-1 a D-5 (plan Starter, base nueva, repositorio privado, inventario de variables de la 2.0.0, fecha) | PENDIENTE | Repositorio **público** (API de GitHub) | Responsable | Lanzamiento §0 | Decisiones por escrito | — |
| G-25 | IP real del usuario en el registro (R-14) y fuentes de datos desde Frankfurt (R-13) | PENDIENTE | `T28.test_forwarded_for_*` | Responsable | Lanzamiento §7, H-9 | La IP coincide | — |
| G-26 | Presentación como herramienta de análisis: la estrategia no tiene ventaja demostrada (R-12) | MITIGADO | `INFORME_VENTAJA.md`; `T32…no_promises…` | Responsable | — | Ninguna comunicación con cifras de rentabilidad | Permanente |

**Resumen:**
- 13 CERRADOS: G-01 a G-12 y G-14.
- 4 MITIGADOS: G-13, G-15, G-19 y G-26.
- 8 PENDIENTES: G-17, G-18 y G-20 a G-25.
- 1 BLOQUEANTE: G-16.

## Qué hace falta para pasar a GO

1. **G-16:** completar los datos del responsable y obtener la revisión jurídica de la política.
2. **G-24:** las decisiones D-1 a D-5 por escrito.
3. Autorización expresa para ejecutar `PROCEDIMIENTO_LANZAMIENTO_PILOTO.md`. Durante ese procedimiento se cierran
   G-17, G-18, G-20, G-22, G-21, G-23 y G-25, en ese orden.
4. Si todo se cumple, se abre la **fase 1** (3 a 5 usuarios internos) y este documento se actualiza a GO con la fecha y
   las evidencias reales.
