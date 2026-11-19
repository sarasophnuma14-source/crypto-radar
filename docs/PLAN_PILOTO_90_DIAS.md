# Plan de piloto de 90 días · Crypto Radar 2.1

Fecha: 16 de noviembre de 2026.

**Objetivo:** reemplazar por datos los supuestos de `UNIT_ECONOMICS.md` y `MODELO_NEGOCIO_VALIDADO.md`, en especial cuatro:

- uso;
- retención;
- disposición a pagar;
- costo de conseguir cada usuario.

**Reglas del piloto:**

- **Cerrado:** solo con solicitud y aprobación manual (existe: `REGISTRO_USUARIOS_PILOTO.md`).
- **Gratuito:** pagos desactivados (G-09).
- Sin promesas de rentabilidad.
- Sin cambios en el motor cuantitativo ni en el holdout.
- Duración de 60 a 90 días. La decisión se toma al día 60 si los datos ya son concluyentes; si no, al día 90.

## 0. Condiciones para abrir el piloto (día 0)

El piloto **no puede abrir** mientras `GO_NO_GO_PILOTO.md` siga en NO-GO. Bloquean hoy:

| Requisito | Estado | Quién |
|---|---|---|
| G-16: texto legal de privacidad completo y revisado (10 marcadores COMPLETAR) | BLOQUEANTE | PATRON + abogado |
| TOTP del administrador inscrito y `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` eliminado | PENDIENTE (el registro de las 02:34Z dice «vigente») | PATRON |
| Rotación de la contraseña `radar_app` y del token de Telegram | PENDIENTE | PATRON |
| `/healthz` configurado como *health check* en Render, con la PR #12 desplegada | PENDIENTE de autorización | PATRON |
| Copia de seguridad automática programada y una restauración probada | PENDIENTE | Equipo + PATRON |
| Plan de Neon confirmado (el Free **no sirve**: `UNIT_ECONOMICS.md` §5) | PENDIENTE | PATRON |
| Landing honesta (PR #11) aprobada y publicada | PENDIENTE de autorización | PATRON |

## 1. Qué se puede medir hoy y qué no (MEDIDO en el código)

| Métrica | ¿Se puede medir hoy? | Fuente |
|---|---|---|
| Solicitudes, aprobaciones y rechazos | Sí | `users.created_at`, `status`, `approved_at` |
| Inicios de sesión | Sí | tabla `activity`, acción `login` |
| Telegram vinculado | Sí | `activity`: `telegram_linked` / `telegram_unlinked`; `users.telegram_chat_id` |
| Posiciones registradas en la cartera | Sí | `activity`: `position_add`; tabla `positions` |
| **Uso diario o semanal** (quién abrió la app un día dado) | **No** | La sesión dura 14 días (`SESSION_DAYS = 14`), así que un usuario puede usar la app dos semanas sin generar ni un `login` |
| Qué pestañas se usan y exportaciones CSV | **No** | No se registra |
| Alertas de Telegram entregadas por usuario | Parcial | Solo en los registros del servidor |
| Disposición a pagar | **No** | Requiere encuesta (§4) |

**Instrumentación necesaria antes del día 0** (cambio pequeño; no toca el motor; requiere autorización para desplegar):

1. Registrar en `activity` un evento `visit` **como máximo una vez por usuario y día**, al primer pedido autenticado del día. Sin IP adicional ni contenido.
2. Registrar `export_csv` y `tab:<nombre>` como máximo una vez por usuario y día.
3. Un informe para el administrador con las métricas del §3, calculadas con SQL sobre `activity`. Sin herramientas externas de analítica: no se añaden terceros que reciban datos de usuarios.

La política de privacidad (G-16) debe mencionar este registro de uso.

**Estado (16-nov-2026):** implementada en el PR #14 (`radar/piloto.py`), **apagada**. Se enciende con `CRYPTO_RADAR_PILOT_METRICS=1`, y las encuestas además con `CRYPTO_RADAR_PILOT_SURVEYS=1`, solo tras G-16 y con autorización.

Definición operativa: «activo» en una ventana de retención significa **al menos un día con `visit`** dentro de la ventana. Las cohortes son semanales (semana ISO del primer inicio de sesión).

## 2. Tamaño y reclutamiento

**Meta:** 50 a 100 usuarios aprobados, para llegar a **30 o más activados**, el mínimo para que las tasas signifiquen algo.

Con 30 usuarios, una tasa observada del 40 % tiene un intervalo de confianza del 95 % de aproximadamente 23 % a 58 %. Las decisiones deben leerse con ese margen; no hay que sobreinterpretar diferencias pequeñas.

Fuentes de solicitudes, todas orgánicas (§6). A cada solicitud se le pregunta **cómo conoció el producto**. El formulario actual tiene `request_note`; se puede pedir ahí sin cambiar código.

## 3. Métricas y umbrales

**Definiciones:**

- **Activado:** inicia sesión y, en sus primeros 7 días, vincula Telegram **o** registra una posición **o** visita la app en 3 días distintos.
- **Activo semanal:** al menos 2 días con `visit` en la semana.

| Métrica | Fórmula | Umbral para GO (ver `DECISION_COMERCIAL_GO_NO_GO.md`) |
|---|---|---|
| Activación | activados ÷ aprobados | ≥ 50 % |
| Retención a 30 días | activos en los días 22 a 30 ÷ activados de la cohorte | ≥ 35 % |
| Retención a 60 días | activos en los días 52 a 60 ÷ activados | ≥ 25 % |
| Uso semanal | promedio de días con `visit` por activo semanal | ≥ 2,5 |
| Telegram vinculado | vinculados ÷ activados | ≥ 40 % (indicador de valor de las alertas) |
| Prueba de «decepción» (§4) | «muy decepcionado» ÷ respuestas | ≥ 40 % |
| Intención de pago a US$15 | «sí, seguro» + «probablemente sí» ÷ activos a 30 días | ≥ 30 % |
| Precio aceptable | mediana de Van Westendorp entre «barato» y «caro» | Incluye US$15 |

## 4. Disposición a pagar y retención: cómo se pregunta

Las encuestas se hacen dentro de la app o por un formulario propio. Sin incentivos que sesguen las respuestas y sin decir que habrá descuento por responder.

**Día 14, uso:**

- ¿Para qué lo usas?
- ¿Qué te sobra?
- ¿Qué te falta?

**Día 30, disposición a pagar:**

1. Las cuatro preguntas de Van Westendorp:
   - a qué precio sería tan barato que dudarías de la calidad;
   - a qué precio sería una ganga;
   - a qué precio empezaría a ser caro;
   - a qué precio sería demasiado caro.
2. «Si Crypto Radar Pro costara US$15 al mes (o US$149 al año), ¿lo pagarías?» Respuestas: seguro que sí / probablemente sí / no sé / probablemente no / seguro que no.
3. «¿Mensual o anual?»
4. «¿Qué herramienta dejarías de pagar o de usar si lo pagas?»

**Día 45, prueba de decepción:** «¿Cómo te sentirías si ya no pudieras usar Crypto Radar?» Respuestas: muy decepcionado / algo decepcionado / nada.

**Día 60, Élite:** «De esta lista, ¿cuáles pagarías aparte?» La lista es la de candidatos de `MODELO_NEGOCIO_VALIDADO.md` §4. Se pide orden de preferencia y una pregunta abierta.

**Señal de compromiso sin cobrar:** al día 60, ofrecer «avisarme cuando abra Pro a US$15». Es una lista de interés, **sin pago ni reserva con dinero** (los pagos siguen apagados). Cuenta como señal más fuerte que la encuesta.

Advertencia: la intención declarada sobreestima la compra real. Por eso el GO exige además una primera cohorte de pago pequeña y controlada (`DECISION_COMERCIAL_GO_NO_GO.md` §3).

## 5. Calendario

| Días | Actividad | Salida |
|---|---|---|
| −14 a 0 | Cerrar las condiciones del §0 e instrumentar el §1 | Piloto en GO |
| 0 a 14 | Aprobar por tandas de 10 a 20 personas; acompañar la incorporación | Activación de las primeras cohortes |
| 14 | Encuesta de uso | Lista de fricciones |
| 15 a 30 | Corregir fricciones de UX sin tocar el motor cuantitativo | — |
| 30 | Encuesta de disposición a pagar; retención a 30 días de la primera cohorte | Primer informe de métricas |
| 45 | Prueba de decepción | — |
| 60 | Encuesta de Élite; lista de interés; **revisión GO/NO-GO** | Decisión o extensión a 90 días |
| 90 | Revisión final si se extendió | Decisión |

## 6. Adquisición orgánica (piloto y lanzamiento)

Con un CAC sano por debajo de US$20 a US$30 (`UNIT_ECONOMICS.md` §7), los anuncios pagados no son la primera opción. Canales, todos con atribución en la solicitud:

1. **Transparencia como contenido:**
   - informe semanal público con el ranking, sus limitaciones y la tabla de resultados, **incluidos los negativos**;
   - el resultado NO EDGE contado sin maquillaje es un diferenciador frente a canales de «señales».
2. **Comunidades en español** (Telegram, X, Reddit, Discord): participar con análisis útiles, sin promesas y sin *spam*.
3. **Referidos de usuarios del piloto:** cada usuario activo puede recomendar hasta 3 personas, aprobadas manualmente. No hay código de referidos: se anota en `request_note`.
4. **SEO de largo plazo:** guías en español sobre *funding*, métricas de derivados y cómo leer un ranking. Ninguna promete resultados.

**CAC orgánico:** se registran las horas por canal. Horas × valor hora (a definir por PATRON) ÷ usuarios activados por canal.

## 7. Qué se entrega al final

Un informe con:

- todas las métricas del §3 y sus intervalos;
- los resultados de las encuestas;
- el embudo por canal;
- el consumo real de Neon y de las llamadas a CoinGecko;
- la recomendación GO o NO-GO según `DECISION_COMERCIAL_GO_NO_GO.md`.

Los datos negativos se reportan igual que los positivos.
