# Informe de la prueba de 10 usuarios · 2.1.0

Fecha: 2026-11-16. **Estado: NO EJECUTADA en Render + Neon.** El servicio 2.1 no existe todavía. Nada de lo que sigue
es una validación de Render.

## Ensayos locales (no son Render)

Con 0,5 CPU emulada mediante un cgroup, igual que Render Starter, SQLite local y sin red:

| Ensayo | Inicio de sesión p95 | Panel p95 | 5xx | 429 | > 2 s | Entran | Resultado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Inicio de sesión escalonado (1 por segundo) | 110,9 ms | 9,3 ms | 0 | 0 | 0 | 10/10 | APROBADO |
| Inicio de sesión en ráfaga (los 10 a la vez) | 1 194 ms | 11,5 ms | 0 | 0 | 0 | 10/10 | APROBADO |

Evidencia: `evidencia_piloto/preparacion/prueba_10_ensayo_local.json` y `prueba_10_ensayo_local_rafaga.json`.

## Prueba real pendiente

Script: `tests/piloto/prueba_render_10.py` (`PROCEDIMIENTO_LANZAMIENTO_PILOTO.md` §8).
1. Crear y aprobar las cuentas `prueba01` a `prueba10` desde el panel del administrador.
2. Ejecutar la prueba desde una máquina de confianza, con `CR_BASE` y `CR_PASSWORD` exportadas:
   `python tests/piloto/prueba_render_10.py --usuarios prueba01,…,prueba10 --minutos 5 salida.json`.
3. Repetirla durante un escaneo.

**Criterios de aprobación:**
- p95 < 1 s;
- 0 respuestas 5xx y 0 respuestas 429;
- ninguna petición > 2 s;
- los 10 usuarios entran;
- ningún usuario heredado puede autenticarse (la base es nueva: 0 registros heredados);
- 1 solo administrador;
- pagos en `off`, con `POST /api/billing/checkout` → 503.

Al terminar, las cuentas de prueba se desactivan.
