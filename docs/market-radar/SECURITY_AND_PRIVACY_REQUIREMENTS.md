# Requisitos de seguridad y privacidad · Market Radar

Versión 1.0 · 18-nov-2026.
Regla previa: **se resuelven primero los bloqueos conocidos de Crypto Radar 2.1** (Fase 0). Las pruebas locales no demuestran seguridad en producción.

## 1. Bloqueos heredados (Fase 0)

| Id | Bloqueo | Estado al 16-nov (fase cero) | Cierre exigido |
|---|---|---|---|
| S0-1 | TOTP del administrador no inscrito; código de alta vigente | Abierto | TOTP activo + variable `CRYPTO_RADAR_ADMIN_ENROLL_TOKEN` borrada + registro de arranque sin "vigente" |
| S0-2 | Contraseña de `radar_app` y token de Telegram expuestos en el chat | Abierto | Rotados, con fecha registrada |
| S0-3 | Health check vacío en Render | Abierto | `/healthz` configurado |
| S0-4 | Repositorio público con identificadores de infraestructura | Abierto | Privado (acción irreversible, decide PATRON) |
| S0-5 | 2.0 activa | Abierto | Copia verificada + suspensión autorizada |
| S0-6 | Sin copias automáticas | Abierto | Diarias, cifradas, externas, con restauración probada |
| S0-7 | Política de privacidad con marcadores COMPLETAR | Abierto | Datos del responsable reales + revisión de abogado |
| S0-8 | Sin CI | Abierto | Suite en cada PR |

## 2. Identidad y acceso

| Id | Requisito |
|---|---|
| S-01 | TOTP obligatorio para cualquier cuenta con rol de administración (reutiliza `radar/totp.py`) |
| S-02 | Roles mínimos: `user`, `analyst_admin` (mercados, licencias), `ops_admin` (operación). Ningún rol tiene acceso a secretos |
| S-03 | Sesiones con token aleatorio, solo hash en base, `HttpOnly; Secure; SameSite=Lax`, expiración y revocación por usuario |
| S-04 | Bloqueo tras intentos fallidos y rate limiting por IP y cuenta, compartido en base |
| S-05 | Reautenticación con TOTP para: cambiar licencias, habilitar mercados, cambiar versiones del score, exportar datos de usuarios |
| S-06 | Registro de accesos administrativos en `audit_events` con hash encadenado |

## 3. Secretos

| Id | Requisito |
|---|---|
| S-10 | Ninguna contraseña, token ni clave de proveedor en el repositorio, en documentos ni en el chat |
| S-11 | Claves de proveedor solo como variables de entorno del servicio que las usa (worker); la web no las recibe |
| S-12 | Rotación: claves de proveedor cada 180 días o ante sospecha; credenciales de base cada 90 días; procedimiento escrito y probado |
| S-13 | Escaneo de secretos en CI (p. ej. gitleaks) antes de fusionar |
| S-14 | Los secretos TOTP se cifran con clave separada (`CRYPTO_RADAR_TOTP_KEY`, ya existente) |

## 4. Aplicación y API

| Id | Requisito |
|---|---|
| S-20 | CSRF en toda petición que cambia estado; POST solo JSON del mismo origen |
| S-21 | CSP estricta, `nosniff`, `frame-ancestors 'none'` |
| S-22 | Validación de esquema en toda entrada de `/api/v1`; tamaño máximo de cuerpo |
| S-23 | Toda consulta de datos de usuario filtra por `user_id` (prueba automática por endpoint) |
| S-24 | Endpoints públicos sin veredicto ni señales (corrige fase cero A-7) |
| S-25 | Rate limiting por endpoint y por usuario; respuestas 429 con `Retry-After` |
| S-26 | Errores sin trazas internas hacia el cliente |

## 5. Datos de proveedores

| Id | Requisito |
|---|---|
| S-30 | `provider_licenses` controla almacenamiento, visualización y exportación (ver `DATA_LICENSE_MATRIX.md` §4) |
| S-31 | Las respuestas de proveedores se validan (tipos, rangos, OHLC coherente) antes de guardarse |
| S-32 | Los textos de proveedores (nombres, noticias) se escapan siempre al mostrarlos |

## 6. Inteligencia artificial

| Id | Requisito |
|---|---|
| S-40 | El contenido externo (noticias, páginas, descripciones) va a la IA marcado como **datos**, separado de las instrucciones, y nunca puede cambiar herramientas, permisos ni destinatarios |
| S-41 | La IA no tiene herramientas de escritura ni acceso a secretos, datos de otros usuarios o red abierta |
| S-42 | Validación de salida: cifras deben coincidir con las entradas; enlaces solo a fuentes de la entrada; si falla, se descarta |
| S-43 | No se envían datos personales al proveedor de IA más allá de lo necesario; las carteras se envían agregadas sin identificador de usuario |
| S-44 | Registro de modelo, versión, hash del prompt y referencias de entrada; sin texto personal en los registros |
| S-45 | Límite de uso por usuario y presupuesto mensual global con corte automático |

## 7. Telegram

| Id | Requisito |
|---|---|
| S-50 | Vinculación por código de un solo uso con expiración (ya existe), limitada por chat |
| S-51 | Mensajes sin datos personales ni de cartera salvo que el usuario lo active |
| S-52 | Token del bot rotado tras S0-2 y almacenado solo en el worker |

## 8. Infraestructura y operación

| Id | Requisito |
|---|---|
| S-60 | Mínimo privilegio en base: rol de aplicación sin DDL; rol de migraciones separado; rol de copia de solo lectura (ya hecho en la 2.1: `radar_app`, `radar_backup`) |
| S-61 | Copias diarias cifradas (p. ej. `age`) fuera del proveedor de base; retención 30 días; restauración probada cada mes en una base vacía con comparación |
| S-62 | `/livez` y `/readyz`; health check configurado en Render |
| S-63 | Observabilidad sin datos personales; alertas operativas al administrador |
| S-64 | Dependencias fijadas, `pip-audit` en CI, revisión mensual |
| S-65 | Revisión trimestral de permisos (GitHub, Render, Neon, proveedores, Telegram) |

## 9. Privacidad

Marco aplicable más probable: **Ley 1581 de 2012 de Colombia** (protección de datos personales) por el domicilio previsto del responsable; posibles obligaciones adicionales si hay usuarios en la UE (RGPD) u otros países. **NO VERIFICADO jurídicamente:** requiere abogado.

| Id | Requisito |
|---|---|
| S-70 | Política de privacidad completa con responsable identificado; **no se inventan datos de la empresa** |
| S-71 | Datos mínimos: correo, hash de contraseña, preferencias, watchlists, carteras declaradas, chat de Telegram si se vincula |
| S-72 | Consentimiento versionado (ya existe `POLICY_VERSION`) |
| S-73 | Retención: cuentas inactivas 24 meses → aviso → borrado; registros de actividad 12 meses; `audit_events` administrativos 5 años (SUPUESTO, validar con abogado) |
| S-74 | Derecho de acceso, rectificación y borrado: exportación y borrado de cuenta desde la interfaz, con efecto en copias al expirar su retención |
| S-75 | Carteras: dato sensible desde el punto de vista financiero; cifrado a nivel de columna evaluado en Fase 2 |
| S-76 | Transferencias internacionales: Render (región Frankfurt), Neon (Frankfurt), proveedor de IA; documentar en la política |

## 10. Pruebas de seguridad requeridas antes de habilitar cualquier mercado

1. Suite de autorización por endpoint (usuario A no ve datos de B).
2. Prueba de licencias: sin licencia vigente, el dato no aparece en API, interfaz, Telegram ni exportación.
3. Prueba de inyección de instrucciones con noticias maliciosas de muestra (Fase 7).
4. Escaneo de secretos y dependencias en verde.
5. Restauración desde copia en base vacía con comparación sin diferencias.
