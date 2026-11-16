# Privacidad de la instrumentación y las encuestas del piloto

Auditoría correctiva, hallazgo H7 (2026-11-16). Contrasta lo que hace `radar/piloto.py` con la política de privacidad
(`web/privacidad.html`). **No contiene datos legales del propietario ni plazos inventados:** donde hace falta una
decisión suya queda `COMPLETAR` o una variable sin valor por defecto.

La instrumentación sigue **APAGADA** (`CRYPTO_RADAR_PILOT_METRICS` y `CRYPTO_RADAR_PILOT_SURVEYS` sin definir). No debe
encenderse hasta cerrar G-16 (política completa y revisada) y con autorización escrita del propietario.

## 1. Qué datos registra y dónde

| Dato | Tabla | Cuándo | Contenido | Minimización |
|---|---|---|---|---|
| `visit` | `activity` | 1 vez por usuario y día UTC, al primer pedido autenticado | usuario, fecha | `detail` y `ip` siempre `NULL`; id = hash (usuario, evento, día) |
| `tab:<vista>` | `activity` | 1 vez por usuario, vista y día | usuario, vista, fecha | solo vistas de una lista cerrada (`TABS`) |
| `export_csv` | `activity` | 1 vez por usuario y día | usuario, fecha | no guarda qué se exportó |
| Respuestas a encuestas | `survey_responses` | días 14, 30, 45 y 60 desde la activación, ventana de 14 días | respuestas validadas | escalas y opciones cerradas; texto libre ≤ 500 caracteres **sin correos, enlaces, teléfonos ni usuarios @** (`piloto.redact`) |

No se usan herramientas externas de analítica ni cookies nuevas. Los administradores no generan eventos.

Ya existían antes del piloto y **no** son de la instrumentación: `login`, `telegram_linked`, `position_add` (registro de
seguridad y del producto, cubiertos en la fila «Dirección IP… acciones de seguridad» de la política).

## 2. Quién puede ver qué

| Acceso | Qué ve | Comprobado por |
|---|---|---|
| Administrador (`GET /api/admin/piloto`, requiere sesión de administrador con TOTP: `auth.admin_ok`) | **solo agregados**: recuentos, tasas, intervalos, medias, rangos de precio. Ni ids, ni notas de solicitud, ni texto libre | `test_piloto.PrivacidadH7.test_informe_admin_solo_agregados`, `Informe.test_cohortes_separadas_y_tasas_con_ic` |
| Usuario | sus propias encuestas pendientes; botón «Retirar mis respuestas» en Ajustes | `PrivacidadH7.test_retirar_respuestas` |
| Base de datos (Neon) | todo, incluido el texto libre ya minimizado | acceso restringido a quien tenga la credencial (pendiente R-19: rotar `radar_app`) |

El texto libre **no** se muestra en ninguna pantalla. Si el propietario quiere leerlo, tendría que hacerlo por consulta
directa a la base; eso debe figurar en la política y quedar en el registro de accesos (decisión del propietario).

## 3. Retención y borrado

| Situación | Qué pasa | Código |
|---|---|---|
| Usuario retira sus respuestas | contenido vaciado (`answers = '{}'`), marca `skipped = 2`; la encuesta no se vuelve a ofrecer y cuenta como **no respuesta** | `piloto.withdraw`, `POST /api/piloto/encuesta/retirar` |
| Administrador elimina la cuenta | se borran respuestas y eventos del piloto del usuario **antes** de borrar la cuenta; queda solo un contador anónimo por cohorte (`piloto_bajas`) para que el informe explique por qué sale del denominador | `piloto.forget_user`, `auth.admin_set_status("delete")` |
| Plazo de conservación | `piloto.purge()` borra respuestas y eventos del piloto más antiguos que `CRYPTO_RADAR_PILOT_RETENTION_DAYS`. **Sin valor no borra nada** y el informe muestra el aviso «Retención… sin definir» | `PrivacidadH7.test_retencion_*` |

`purge()` no toca `login`, `telegram_linked` ni `position_add`. Los respaldos (`radar/backup.py`) incluyen
`survey_responses`: su retención debe ser coherente con este plazo (ver `docs/RESPALDOS_INDEPENDIENTES.md`).

## 4. Política de privacidad frente a la instrumentación

| Requisito | Antes de esta auditoría | Ahora |
|---|---|---|
| La política menciona los eventos de uso y las encuestas | **No** (incoherente: la política decía qué se trata y esto no estaba) | fila nueva en `web/privacidad.html` §2 que describe exactamente lo de la tabla 1, con el plazo como `COMPLETAR` |
| Finalidad | no declarada | «medir si el piloto funciona… recuentos agregados» |
| Derecho a retirar | no había mecanismo | botón en Ajustes y supresión al eliminar la cuenta |
| Plazo de conservación | no definido | **pendiente del propietario** (`COMPLETAR` en la política y `CRYPTO_RADAR_PILOT_RETENTION_DAYS`) |
| Responsable, NIT, domicilio, correo de derechos | `COMPLETAR` | sigue `COMPLETAR` (G-16). No se inventa |

## 5. Pendiente del propietario

1. Completar los datos del responsable y los plazos de `web/privacidad.html` (G-16) y hacerlos revisar por un abogado.
2. Decidir el plazo de conservación de los datos del piloto y fijarlo en la política y en `CRYPTO_RADAR_PILOT_RETENTION_DAYS`.
3. Decidir si alguien leerá el texto libre por consulta directa y, si es así, declararlo en la política.
4. Autorizar por escrito el encendido de `CRYPTO_RADAR_PILOT_METRICS` y, por separado, `CRYPTO_RADAR_PILOT_SURVEYS`.
