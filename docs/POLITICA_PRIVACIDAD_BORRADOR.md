# Política de tratamiento de datos personales · BORRADOR

**Estado: borrador técnico pendiente de revisión jurídica y de aprobación del responsable.** Este documento no declara
cumplimiento legal. Lo preparó el equipo técnico a partir de lo que el código hace realmente (2026-11-15). Antes de
usarlo, un abogado con experiencia en protección de datos en Colombia debe revisarlo, y el responsable debe completar
todos los campos marcados **[COMPLETAR: …]**. No se ha inventado ningún dato de identificación.

La versión publicada está en `web/privacidad.html`. Debe decir lo mismo que este borrador. `python main.py preflight`
da **BLOQUEANTE** mientras esa página tenga campos `COMPLETAR` o la marca «Borrador pendiente».

Marco que hay que revisar:
- Ley 1581 de 2012.
- Decreto 1377 de 2013, compilado en el Decreto Único 1074 de 2015 (Parte 2, Título 2, Capítulos 25 y 26).
- Decreto 090 de 2018 (Registro Nacional de Bases de Datos).
- Instrucciones de la Superintendencia de Industria y Comercio (SIC) sobre transferencias internacionales.

---

## 1. Responsable del tratamiento

| Campo | Valor |
| --- | --- |
| Nombre o razón social | [COMPLETAR: nombre de la persona natural o razón social] |
| NIT o cédula | [COMPLETAR] |
| Domicilio y dirección | [COMPLETAR] |
| Representante legal (si es sociedad) | [COMPLETAR] |
| Correo para consultas y reclamos | [COMPLETAR: correo dedicado y vigilado] |
| Teléfono u otro canal | [COMPLETAR] |
| Área o persona que atiende las solicitudes | [COMPLETAR] |

## 2. Alcance y piloto cerrado

Esta política se aplica a los datos que trata Crypto Radar 2.1.0 (web y bot de Telegram).

**Piloto cerrado:**
- el acceso requiere la aprobación manual del administrador;
- el número de personas es limitado;
- no se cobra nada;
- el servicio es una herramienta de análisis en pruebas y puede tener fallos;
- no es asesoría financiera ni promete resultados.

**Versión anterior (2.0.0).** La 2.1.0 empieza como plataforma nueva:
- ninguna cuenta, contraseña, sesión, token, plan o vínculo de Telegram de la 2.0.0 sirve para entrar;
- si había datos de la versión anterior, el sistema los guarda en un archivo separado, sin contraseñas, sin tokens y
  sin códigos de vinculación;
- ninguna función de acceso lee ese archivo;
- el archivo se conserva durante [COMPLETAR: plazo y motivo legal, contable o de auditoría] y después se elimina.

## 3. Datos tratados y finalidades

| Dato | Finalidad | Origen | Obligatorio |
| --- | --- | --- | --- |
| Usuario y contraseña (solo se guarda el hash scrypt) | Crear la cuenta y autenticar | Titular | Sí |
| Contacto y mensaje de la solicitud | Revisar la solicitud y avisar de la aprobación | Titular | No |
| Fecha y versión de la aceptación de esta política | Prueba de la autorización (art. 9 Ley 1581) | Sistema | Sí |
| IP, navegador, fecha y acciones de seguridad (inicios de sesión, fallos, aprobaciones, cambios de contraseña o de TOTP) | Seguridad, prevención de fraude, límites de intentos y auditoría de acciones administrativas | Sistema | Sí |
| Semilla TOTP, si se activa el segundo factor (cifrada) | Verificación en dos pasos | Sistema | Solo administradores |
| Ajustes (capital de referencia, riesgo por operación, lista de seguimiento) y posiciones registradas a mano | Calcular tamaños de posición y mostrar la cartera simulada. No hay conexión con cuentas de exchange | Titular | No |
| Identificador de chat de Telegram | Enviar alertas y responder comandos | Titular, al vincular | No |
| Referencia, plan, monto y estado de pagos | Activar planes y contabilidad. **Durante el piloto no hay pagos** | Proveedor de pagos | Solo si hay pagos |
| Comentarios y reportes de fallos del piloto | Corregir errores | Titular | No |

No se tratan datos sensibles (art. 5 Ley 1581) ni datos de menores. El servicio es solo para mayores de 18 años.
[COMPLETAR: decidir cómo se verifica la mayoría de edad. Hoy solo se declara al aceptar.]

## 4. Autorización

La autorización es previa, expresa e informada. Se da al marcar la casilla del formulario «Solicitar acceso»
(`/entrar#solicitar`), que enlaza esta política y el aviso de riesgo. Sin la casilla no se crea la solicitud. El
sistema guarda la fecha y la versión aceptada (`consent_at` y `consent_version`) como prueba.

Cuando se apruebe el texto definitivo, cambia `POLICY_VERSION` en `radar/auth.py` y el valor de la casilla en
`web/entrar.html`. Así, las personas que aceptaron el borrador vuelven a aceptar la versión final.

## 5. Aviso de privacidad (texto corto para el formulario)

> [COMPLETAR: responsable], con domicilio en [COMPLETAR], tratará tus datos (usuario, contraseña cifrada, contacto
> opcional, datos técnicos de seguridad y, si lo vinculas, tu chat de Telegram) para crear y proteger tu cuenta del
> piloto cerrado de Crypto Radar y enviarte las alertas que pidas. Tus datos pueden alojarse en servidores fuera de
> Colombia (Render, Neon y, si lo usas, Telegram). Puedes conocer, actualizar, rectificar y suprimir tus datos y
> revocar la autorización escribiendo a [COMPLETAR: correo]. Política completa: /privacidad.

## 6. Encargados, terceros y transferencias internacionales

| Proveedor | Qué recibe | Ubicación | Papel | Pendiente |
| --- | --- | --- | --- | --- |
| Render | Todo el tráfico y el servidor | Frankfurt, Alemania (`render.yaml`: `region: frankfurt`) | Encargado (alojamiento) | Revisar sus términos y su anexo de tratamiento de datos; documentar la transmisión |
| Neon | Base de datos completa | [COMPLETAR: región del proyecto] | Encargado (base de datos) | Ídem |
| Telegram | Chat id y contenido de las alertas, solo si el titular vincula su chat | Fuera de Colombia | Tercero con su propia política: el titular usa su propia cuenta de Telegram | Informar en el formulario de vinculación |
| Google Fonts | IP del navegador al cargar las tipografías | Fuera de Colombia | Tercero | Valorar servir las fuentes desde el propio servidor para evitarlo |
| Wompi y NOWPayments | Datos de pago | [COMPLETAR] | Responsables o encargados según su contrato | **No aplica durante el piloto: pagos desactivados** |

Comprobaciones jurídicas pendientes:
- **Transmisión o transferencia.** Si Render y Neon actúan como encargados, hay una transmisión internacional que
  requiere un contrato o cláusulas de transmisión (Decreto 1074 de 2015, art. 2.2.2.25.5.2). Si es una transferencia,
  aplica el art. 26 de la Ley 1581 (país con nivel adecuado o autorización del titular).
- **Nivel adecuado.** Verificar el país de cada región elegida frente a la lista vigente de la SIC.
- **Venta o cesión.** No se venden ni se ceden datos para publicidad.

## 7. Derechos del titular (art. 8 Ley 1581) y procedimiento

El titular puede:
- conocer, actualizar y rectificar sus datos;
- pedir prueba de la autorización;
- ser informado del uso de sus datos;
- presentar quejas ante la SIC, una vez agotado el trámite ante el responsable (art. 16);
- revocar la autorización o pedir la supresión cuando no exista un deber legal o contractual de conservar el dato;
- acceder gratis a sus datos.

| Trámite | Plazo | Prórroga |
| --- | --- | --- |
| Consulta (art. 14) | 10 días hábiles | 5 días hábiles, informando el motivo |
| Reclamo (art. 15) | 15 días hábiles | 8 días hábiles, informando el motivo |
| Reclamo incompleto | Se pide completarlo en 5 días | Desistimiento si no se completa en 2 meses |

Procedimiento interno, en `docs/REGISTRO_USUARIOS_PILOTO.md` §6:
1. Recibir la solicitud por el correo del §1.
2. Verificar la identidad.
3. Responder dentro del plazo.
4. Registrar la respuesta.

Hoy **no hay** exportación ni supresión automática de datos en el panel. El administrador las hace con
procedimientos documentados. [COMPLETAR: decidir si se automatiza antes de ampliar el piloto.]

## 8. Conservación y supresión

| Dato | Plazo propuesto (a decidir) |
| --- | --- |
| Cuenta y ajustes | Mientras exista la cuenta; supresión en [COMPLETAR] días tras la solicitud |
| Registro de actividad y seguridad | [COMPLETAR: p. ej. 12 meses] |
| Pagos | El plazo que exija la normativa contable y tributaria [COMPLETAR] |
| Archivo de la 2.0.0 | [COMPLETAR] |
| Copias de seguridad | 7 diarias y 4 semanales (`PLAN_BACKUP_RECUPERACION.md` §5). Un dato suprimido desaparece de las copias cuando estas caducan |

## 9. Seguridad

Medidas que existen en el código y están probadas:
- HTTPS con HSTS;
- contraseñas con scrypt;
- sesiones guardadas solo como hash, con cookie `HttpOnly`, `Secure` y `SameSite`;
- protección CSRF;
- límites de intentos;
- verificación en dos pasos obligatoria para el administrador, con alta mediante un código de un solo uso;
- semillas TOTP cifradas;
- copias firmadas con HMAC;
- registro de acciones administrativas.

Hay que revisar el texto de las cookies (§10) para que coincida con la configuración desplegada.

## 10. Cookies

Solo existe una cookie técnica de sesión, `cr_session`, imprescindible para mantener la sesión. No hay cookies de
publicidad ni de analítica.

## 11. Registro Nacional de Bases de Datos (RNBD)

La inscripción es obligatoria para sociedades y entidades sin ánimo de lucro con activos totales superiores a 100 000
UVT (Decreto 090 de 2018). [COMPLETAR: el abogado confirma si aplica según la forma jurídica del responsable.]

## 12. Vigencia y cambios

Versión [COMPLETAR: fecha de aprobación]. Si cambia una finalidad, se pide una nueva autorización (§4).

---

## Lista de verificación para la aprobación humana

| # | Punto | Quién | Estado |
| --- | --- | --- | --- |
| P-1 | Completar los datos del §1 en este documento y en `web/privacidad.html` | Responsable | PENDIENTE |
| P-2 | Revisión jurídica del texto completo | Abogado | PENDIENTE |
| P-3 | Plazos de conservación del §8 y del archivo de la 2.0.0 | Responsable con el abogado | PENDIENTE |
| P-4 | Regiones de Render y Neon, y su documentación de transmisión | Responsable | PENDIENTE |
| P-5 | Decidir si se inscribe en el RNBD | Abogado | PENDIENTE |
| P-6 | Correo de consultas operativo y procedimiento interno de respuesta | Responsable | PENDIENTE |
| P-7 | Cambiar `POLICY_VERSION` y el valor de la casilla al publicar el texto final | Equipo técnico | PENDIENTE (después de P-1 y P-2) |
