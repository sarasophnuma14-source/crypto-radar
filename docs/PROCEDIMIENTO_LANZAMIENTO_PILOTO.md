# Procedimiento de lanzamiento del piloto cerrado · Crypto Radar 2.1.0

Fecha: 2026-11-15. **No se ha ejecutado nada de esto en producción.** Cada paso que toca Render, Neon, GitHub o
datos reales necesita la autorización expresa del responsable y lo ejecuta él (o alguien en su nombre, con permiso
escrito). Cada paso tiene un criterio de aceptación: si no se cumple, no se pasa al siguiente.

Antes de empezar, `GO_NO_GO_PILOTO.md` debe decir **GO**. Hoy dice **NO-GO** por los bloqueantes no técnicos.

## 0. Decisiones previas (responsable)

| # | Decisión | Recomendación |
| --- | --- | --- |
| D-1 | Plan de Render | Starter (0,5 CPU) |
| D-2 | Base de datos de la 2.1 | **Nueva** en Neon, vacía, en una región cercana a Frankfurt |
| D-3 | Texto legal de privacidad | Completarlo y que lo revise un abogado (`POLITICA_PRIVACIDAD_BORRADOR.md`) |
| D-4 | Repositorio | Pasarlo a privado |
| D-5 | Fecha y hora del despliegue | Un día laborable por la mañana (Bogotá), con 2 h libres |

## 1. Orden de integración

`PLAN_INTEGRACION_GIT.md` §3:
1. Desactivar el despliegue automático de Render.
2. Fusionar #3 → #4 → #5 → #6 → #7 → #8 con *merge commit*, nunca con *squash*.
3. Comprobar que `main` es idéntico a `claude/preparacion-piloto`.
4. Pasar la regresión completa sobre `main`.

**Criterio:** `git diff origin/main origin/claude/preparacion-piloto` vacío, y `test_suite`, `test_edge` y `test_paper`
en verde.

## 2. Copia previa

- Base de la 2.0.0, si existe: crear una rama en Neon y hacer una copia firmada (`PLAN_BACKUP_RECUPERACION.md` §1).
- Inventario de las variables actuales de Render (`PROCEDIMIENTO_ROLLBACK.md` §2.1).

**Criterio:** `backup verify` OK y el inventario guardado en el gestor de contraseñas.

## 3. Validación previa

En la máquina de confianza, con las variables **reales** exportadas:

```bash
python main.py preflight          # 0 BLOQUEANTES
python main.py preflight --db     # sobre la base nueva: «base vacía: se marcará como 2.1 al arrancar»
```

**Criterio:** 0 bloqueantes. Las advertencias se revisan una a una. Las aceptables el día del despliegue son
`CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` definido, `TOTP del administrador: pendiente` y Telegram sin token.

## 4. Configuración de seguridad en Render

Variables y valores en `CONFIGURACION_RENDER_NEON.md` §2:
- generar `CRYPTO_RADAR_TOTP_KEY` y `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` en el ordenador del responsable;
- `CRYPTO_RADAR_BACKUP_KEY` **no** va en Render.

**Criterio:** el preflight con esas variables da 0 bloqueantes.

## 5. Despliegue

1. Volver a activar el despliegue y desplegar `main` **una vez**.
2. En el registro deben aparecer, en este orden:
   - `Modo cuentas activo · base de datos postgresql · esquema verificado`
   - `Plataforma 2.1 · inicialización: nueva · … · piloto cerrado`
   - `Administrador: <usuario> · creado`
   - `Código de alta del administrador …: registrado (vale 24 h, un solo uso)`
   - `Crypto Radar 2.1.0 en …`

**Criterio:** todas las líneas aparecen y no hay ninguna línea `ERROR` ni `No arranco`.

## 6. Bootstrap del administrador

`BOOTSTRAP_ADMIN.md` §3:
1. Entrar con la contraseña.
2. Inscribir el TOTP con el código de alta.
3. Cerrar sesión y volver a entrar con TOTP.
4. **Borrar `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN`** y redesplegar.

**Criterio:** `preflight --db` dice «TOTP del administrador en la base: activo» y «Administradores» no aparece como
bloqueante.

## 7. Prueba de humo (15 min)

| # | Comprobación | Esperado |
| --- | --- | --- |
| H-1 | `GET /healthz` | 200, `ok: true` |
| H-2 | `/`, `/entrar`, `/privacidad`, `/aviso-de-riesgo` | 200, con el aviso «Piloto cerrado» en `/entrar` y en precios |
| H-3 | `/app` sin sesión | Redirige a `/entrar` |
| H-4 | Solicitud de una cuenta de prueba | «Solicitud enviada»; no entra hasta que se apruebe |
| H-5 | El administrador la aprueba y la cuenta entra | Plan Libre |
| H-6 | La cuenta de prueba en `/api/admin/users` | 403 |
| H-7 | `POST /api/billing/checkout` | 503, «no configurados» |
| H-8 | El administrador lanza un escaneo | Termina; `/healthz` muestra `last_scan` |
| H-9 | Registro de actividad | Aparecen `access_requested`, `admin_user_approve` y `login` con la IP real del usuario (R-14) |
| H-10 | Cerrar sesión y reutilizar la cookie | 401 |

**Criterio:** todas OK. Si falla H-6 o H-7, rollback inmediato.

## 8. Prueba de 10 usuarios (con autorización)

`tests/piloto/prueba_render_10.py`:
1. Crear hasta 10 cuentas `prueba01` a `prueba10` desde el panel.
2. Con `CR_BASE` y `CR_PASSWORD` exportadas, ejecutar
   `python tests/piloto/prueba_render_10.py --usuarios prueba01,…,prueba10 --minutos 5 salida.json`.
3. Ejecutarla una vez **durante** un escaneo.
4. Desactivar las cuentas al terminar.

**Criterio de aprobación:**
- p95 < 1 s;
- 0 respuestas 5xx;
- ninguna petición > 2 s;
- los 10 entran;
- sin bloqueos de usuarios legítimos (0 respuestas 429);
- sin pérdida de datos: los usuarios y la actividad cuadran después.

Si no se aprueba: no se invita a nadie y se analiza. Si es por CPU, ver el plan (D-1).

## 9. Monitorización y criterios de suspensión

**Diario, durante el piloto:**
- `/healthz`: último escaneo de menos de 5 h y `last_error` vacío;
- registro de Render: líneas `ERROR`, reinicios, 5xx;
- panel de administración: solicitudes nuevas y cuentas activas;
- uso de memoria en Render (umbral: 450 MB);
- copia diaria (`PLAN_BACKUP_RECUPERACION.md` §5).

**Suspender el piloto:** pausar el registro y avisar a los usuarios si ocurre algo de esto:
- **cualquier** acceso indebido: una cuenta que entra sin aprobación, privilegios de administrador en una cuenta que
  no es la del entorno o datos de un usuario visibles para otro;
- pérdida de datos o una copia que no se verifica;
- más del 1 % de respuestas 5xx en un día, o p95 > 2 s sostenido durante más de 1 h;
- reinicios por memoria más de 2 veces en 24 h;
- un fallo del escáner durante más de 24 h;
- una queja de protección de datos sin poder responderla en plazo;
- cualquier comunicación que prometa rentabilidad.

**Volver atrás:** `PROCEDIMIENTO_ROLLBACK.md`.

## 10. Plan del piloto por fases

Cada fase empieza solo si la anterior cumple sus criterios de ampliación. Las métricas se registran a diario en una
tabla simple, de forma manual o con `/healthz` y el panel.

| Fase | Usuarios | Duración sugerida | Quiénes |
| --- | --- | --- | --- |
| 1 | 3 a 5 internos | 7 días | Equipo y personas de confianza que reportan fallos |
| 2 | 10 controlados | 14 días | Invitados conocidos, con canal directo de contacto |
| 3 | 20 | 14 días | Invitados con aprobación individual |
| 4 | Hasta 50 | 21 días o más | Solo si las fases 1 a 3 cumplieron sus criterios |

**Métricas:**
- **Estabilidad:**
  - disponibilidad (`/healthz` OK, como porcentaje del día);
  - p50, p95 y p99 del panel (con la prueba corta semanal y el registro);
  - respuestas 5xx por día;
  - reinicios;
  - memoria máxima;
  - duración de cada escaneo.
- **Calidad de datos:**
  - escaneos completados por día (se esperan 6, uno cada 4 h);
  - fuentes de datos disponibles (`sources` en `/healthz`; Binance o CoinGecko con N/D);
  - antigüedad del último informe;
  - errores del escáner;
  - alertas de Telegram enviadas frente a fallidas.
- **Seguridad y operación:**
  - intentos fallidos y 429 por día;
  - solicitudes pendientes de más de 48 h;
  - copias diarias verificadas;
  - consultas de titulares abiertas.
- **Producto (sin promesas):**
  - usuarios activos por semana;
  - fallos reportados;
  - tiempo de respuesta a los reportes.

No se mide ni se comunica «rentabilidad» de las señales: la estrategia no tiene ventaja demostrada (R-12).

**Criterios para pasar a la fase siguiente:**
- disponibilidad ≥ 99 % en la fase;
- 0 incidentes de acceso indebido;
- 0 pérdidas de datos;
- p95 < 1 s en la prueba semanal;
- 0 respuestas 5xx sostenidas;
- todas las copias diarias verificadas;
- ningún fallo crítico abierto;
- escaneos ≥ 95 % de los previstos.

**Antes de la fase 3:**
- exportación y supresión de datos automatizadas, o un procedimiento manual probado (G-19);
- aviso de solicitudes al administrador.

**Antes de la fase 4:**
- prueba de 50 usuarios en el plan real;
- revisión de capacidad de Neon (conexiones) y del plan de Render.

**Criterios para detener el piloto:** los de suspensión del §9, más cualquier petición del abogado o de la
autoridad.
