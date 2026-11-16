# Riesgos pendientes · 2026-11-16

Complementa `MATRIZ_RIESGOS_PENDIENTES.md` y `GO_NO_GO_PILOTO.md`.

## Plataforma

| ID | Riesgo | Gravedad | Estado | Qué lo cierra |
| --- | --- | --- | --- | --- |
| L-01 | Repositorio **público**: el código y los procedimientos de seguridad están a la vista. No hay credenciales reales en el historial | Alta | PENDIENTE (responsable) | Pasarlo a privado en GitHub → *Settings* |
| L-02 | El servicio de la 2.0.0 sigue `main`: una fusión desplegaría la 2.1 en producción | **Crítica** | MITIGADO a medias: la rama `production-2.0.0` existe; falta cambiar el servicio | `ESTADO_LANZAMIENTO_2_1.md` §2 |
| L-03 | Si la 2.0.0 se gestiona por Blueprint, sincronizarlo con `main` cambiaría sus variables | Alta | PENDIENTE de comprobar en Render | ídem, §2.4 |
| L-04 | Sin acceso a Render ni a Neon: el despliegue, la base, la copia, el TOTP y la prueba de 10 usuarios están sin ejecutar | Alta | BLOQUEADO | Conectores o pasos a mano |
| L-05 | Un rol de Neon creado desde la consola entra en `neon_superuser` | Media | Documentado | Crear `radar_app` por SQL (`CONFIGURACION_NEON_2_1.md` §3) |
| L-06 | En un mismo servidor, un rol puede conectarse a otras bases que no revoquen `CONNECT` | Media | Documentado | Proyecto de Neon **distinto** del de la 2.0.0 |
| G-16 | Política de privacidad sin completar y sin revisión jurídica | **Bloqueante para GO** | POSPUESTO por el responsable | Datos del responsable y revisión del abogado. Mientras tanto, solo instancia interna |

## Estrategia

| ID | Riesgo | Estado |
| --- | --- | --- |
| Q-01 | La estrategia actual no tiene ventaja demostrada (`DECISION_FINAL_EDGE.md`) | Permanente. No se comunica ninguna cifra de rentabilidad |
| Q-02 | No hay ninguna muestra histórica virgen: cualquier mejora futura necesita paper trading sobre datos nuevos | El paper trading de D_volmom espera a la 2.1 desplegada |
| Q-03 | Los costes están modelados, no medidos (sin libro de órdenes histórico) | Propuesta de datos en `INFORME_INVESTIGACION_EDGE.md` §7 |
