# Requisitos de lanzamiento comercial · Crypto Radar 2.1

Fecha: 16 de noviembre de 2026.

Son las condiciones de la **compuerta A** de `DECISION_COMERCIAL_GO_NO_GO.md`. Ninguno se da por cerrado sin evidencia ejecutada.

**Estados:**

- **CERRADO:** hecho y verificado.
- **EN PR:** código listo en una rama, sin fusionar ni desplegar.
- **PENDIENTE:** falta trabajo, acceso o una decisión.
- **BLOQUEANTE:** impide cobrar.

**Responsables:** «PATRON» indica una acción que solo puede hacer el propietario, como cuentas, consolas, contratos o autorizaciones.

## 1. Datos y licencias

| ID | Requisito | Estado | Evidencia hoy | Responsable | Criterio de cierre |
|---|---|---|---|---|---|
| R-01 | Licencia comercial de CoinGecko | BLOQUEANTE | La app usa la API sin clave (MEDIDO). Demo/keyless: uso comercial «Not included». Basic US$35 al mes lo incluye (PÚBLICO, 16-nov-2026) | PATRON (contrato) + equipo (clave en el código) | Plan contratado; la app usa la clave desde una variable de entorno; las llamadas de 7 días caben en el límite del plan |
| R-02 | Atribución de CoinGecko en la UI: «Data provided by CoinGecko» con enlace | BLOQUEANTE | No existe en la UI (MEDIDO: solo hay una mención en el texto de memecoins, sin enlace) | Equipo | Visible donde se muestran sus datos; prueba automática |
| R-03 | Atribución de alternative.me junto al índice Fear & Greed | BLOQUEANTE | No existe en la UI (MEDIDO) | Equipo | Visible junto al dato; prueba automática |
| R-04 | Uso comercial de la API pública de Binance | BLOQUEANTE | Sin respuesta oficial pública (un hilo del foro sin respuesta del equipo) | PATRON (consulta escrita) | Confirmación escrita archivada, o cambio a un proveedor con licencia y costo cotizado |
| R-05 | Uso comercial de la API pública de Bybit | BLOQUEANTE | No verificado | PATRON | ídem R-04 |

## 2. Pagos

Los pagos siguen **desactivados**. Nada de esta sección autoriza activarlos.

| ID | Requisito | Estado | Evidencia hoy | Responsable | Criterio de cierre |
|---|---|---|---|---|---|
| R-06 | Precios del backend alineados con la oferta (Pro 15/149; Élite oculto) | PENDIENTE (requiere autorización) | `radar/billing.py`, `PRICES_USD` = 19/190 y 39/390 (MEDIDO) | Equipo, tras autorización | Prueba: el *checkout* de Pro cobra 1500 o 14900 centavos; Élite no se ofrece |
| R-07 | Prueba en *sandbox* real de Wompi y NOWPayments | PENDIENTE | Nunca probado contra el proveedor (R-03 del piloto) | Equipo + PATRON (credenciales de prueba, sin pegarlas en el chat) | Un cobro aprobado, uno rechazado y un *webhook* repetido en cada proveedor, con plan otorgado una sola vez |
| R-08 | Comisiones reales confirmadas por escrito | PENDIENTE | Tarifas de prensa (Wompi) y de la base de conocimiento (NOWPayments) | PATRON | Contrato o tarifa en la cuenta del comercio |
| R-09 | **Reembolso o anulación revocan el plan** | BLOQUEANTE | No existe (MEDIDO): los *webhooks* solo actualizan el estado de pagos sin verificar (`verified = 0`); un pago aprobado y luego reembolsado **conserva el plan** | Equipo | Prueba: aprobado → plan; reembolsado o anulado → plan revocado y registrado en `activity` |
| R-10 | Política de reembolso publicada (14 días, completo) | PENDIENTE | No existe | PATRON + abogado | Página publicada y enlazada desde el *checkout* |
| R-11 | Cancelación de la suscripción por el usuario desde la app | PENDIENTE | Los planes tienen `plan_until`; no hay cobro recurrente automático (MEDIDO), así que «cancelar» equivale a no renovar | Equipo | Texto claro en la cuenta: qué pasa al vencer y cómo renovar |

## 3. Legal, fiscal y contable

| ID | Requisito | Estado | Evidencia hoy | Responsable | Criterio de cierre |
|---|---|---|---|---|---|
| R-12 | Política de privacidad completa y revisada (G-16) | BLOQUEANTE | 10 marcadores COMPLETAR en `/privacidad` (auditoría, A-5) | PATRON + abogado | Sin marcadores; revisión firmada; menciona el registro de uso del piloto |
| R-13 | Términos y condiciones | BLOQUEANTE | No hay página de términos: solo `/privacidad` y `/aviso-de-riesgo` (MEDIDO, `LEGAL_PAGES`) | PATRON + abogado | Página publicada; aceptación registrada al pagar |
| R-14 | Concepto legal: herramienta informativa frente a asesoría de inversión | BLOQUEANTE | Sin concepto | Abogado | Concepto escrito para los países donde se venderá |
| R-15 | Tratamiento de IVA, retenciones e impuesto de renta | BLOQUEANTE | Sin concepto. `UNIT_ECONOMICS.md` muestra el impacto con y sin IVA | Contador | Concepto escrito; precio final definido con o sin IVA |
| R-16 | Facturación electrónica DIAN (si aplica) | BLOQUEANTE | No existe | Contador + PATRON | Proveedor de facturación activo; una factura de prueba emitida |
| R-17 | Ley 1480 (consumidor): sin precio tachado ni «precio de referencia» engañoso | EN PR | La PR #11 muestra el precio de referencia como «precio previsto», sin tachar | PATRON (revisar la PR #11) | Abogado de acuerdo con la presentación del precio |

## 4. Seguridad y operación

| ID | Requisito | Estado | Evidencia hoy | Responsable | Criterio de cierre |
|---|---|---|---|---|---|
| R-18 | TOTP del administrador inscrito; `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` eliminado de Render | BLOQUEANTE | Registro de las 02:34Z: el código está «vigente» | PATRON | Registro de arranque sin «vigente»; la variable no existe |
| R-19 | Rotación de la contraseña `radar_app` de Neon y del token de Telegram | BLOQUEANTE | Sin confirmar (auditoría, C-4) | PATRON | Fecha de rotación anotada; la app arranca con las nuevas credenciales |
| R-20 | *Health check* de Render en `/healthz`, con la readiness real | EN PR | PR #12: 503 en 3 s con la base caída (probado en local) | PATRON (autorizar el despliegue; configurar la ruta) | Render muestra el *health check* activo; prueba con la base caída en *staging* |
| R-21 | Una sola instancia programa escaneos (bloqueo de líder) | EN PR | PR #12, `radar/leader.py`; probado en PostgreSQL 16 | PATRON (autorizar) | Registro «líder» en una sola instancia |
| R-22 | Lectura parcial de `latest.json` (transferencia de Neon) | EN PR | PR #12, commit `a48500e`; pruebas `LecturaParcial` | PATRON (autorizar) | La transferencia diaria en Neon baja tras el despliegue (`UNIT_ECONOMICS.md` §5) |
| R-23 | Plan de Neon apto para servicio continuo (no Free) | BLOQUEANTE | Plan sin verificar; el Free se agota hacia el día 16 (estimado) | PATRON | Consola de Neon: plan Launch o superior; consumo del mes anotado |
| R-24 | Copias de seguridad automáticas y una restauración probada | BLOQUEANTE | Solo manuales (auditoría, A-3) | Equipo + PATRON | Tarea programada; copia cifrada fuera de Neon; restauración en base vacía verificada |
| R-25 | Suspender el servicio 2.0 | PENDIENTE (requiere autorización) | Sigue activo y escaneando (MEDIDO) | PATRON | Render: servicio suspendido; los datos históricos se conservan |
| R-26 | Repositorio privado | PENDIENTE (requiere autorización) | Público, con identificadores de infraestructura (auditoría, A-4) | PATRON | Visibilidad privada |

## 5. Producto y comunicación

| ID | Requisito | Estado | Evidencia hoy | Responsable | Criterio de cierre |
|---|---|---|---|---|---|
| R-27 | Landing honesta publicada | EN PR | PR #11, 63 comprobaciones | PATRON (revisar y autorizar) | Publicada; la landing antigua de la 2.1 (`web/landing.html`) reemplazada o retirada |
| R-28 | Señales marcadas como no validadas | EN PR | PR #12: barra permanente y detalle | PATRON (autorizar) | Visible en todas las vistas con señales |
| R-29 | Backtest de Élite retirado o mostrado con los resultados negativos | PENDIENTE | Auditoría, C-2 | Equipo, tras decisión | Ninguna cifra retrospectiva positiva sin el resultado NO EDGE al lado |
| R-30 | Élite oculto de la venta hasta tener 2 diferenciadores | PENDIENTE | `MODELO_NEGOCIO_VALIDADO.md` §4 | Equipo, tras autorización | El *checkout* y la página de precios solo ofrecen Pro |
| R-31 | Instrumentación de uso del piloto | PENDIENTE | `PLAN_PILOTO_90_DIAS.md` §1 | Equipo, tras autorización | Eventos `visit`, `export_csv` y `tab:*` registrados una vez por usuario y día; informe para el administrador |

## 6. Resumen

| Estado | Cantidad | IDs |
|---|---|---|
| BLOQUEANTE | 15 | R-01 a R-05, R-09, R-12 a R-16, R-18, R-19, R-23, R-24 |
| EN PR | 6 | R-17, R-20, R-21, R-22, R-27, R-28 |
| PENDIENTE | 10 | R-06 a R-08, R-10, R-11, R-25, R-26, R-29 a R-31 |
| CERRADO | 0 | — |

**Camino más corto** (SUPUESTO de orden, sin fechas porque dependen de terceros):

1. PATRON hace R-18, R-19 y R-23, que son minutos en las consolas.
2. Se revisan y despliegan las PR #11 y #12.
3. En paralelo, se escribe a Binance y Bybit y se piden cotizaciones a contador y abogado.
4. Se contrata CoinGecko Basic solo cuando la compuerta B del piloto esté en GO. Si un piloto gratuito y cerrado ya cuenta como uso comercial no está claro: conviene preguntarlo a CoinGecko al escribirles.
