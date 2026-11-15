# Límites de inicio de sesión · Crypto Radar 2.1.0

Fecha: 2026-11-15. Código: `radar/auth.py` (`login`, `rate_bump`, `rate_peek`) y `radar/server.py` (`client_ip`,
`trusted_proxies`). Pruebas: `T28_RateLimitingCombinado` (16 pruebas) y `T13.test_client_ip_not_spoofable_via_forwarded_for`.

## 1. El problema

Antes había un único límite por IP: **20 inicios de sesión de cualquier tipo cada 15 minutos**, aciertos incluidos.

En la auditoría del piloto (`docs/evidencia_piloto/carga_ip_compartida.json`) se lanzaron 50 inicios de sesión
correctos desde una sola IP, como en una oficina o detrás del CGNAT de un operador móvil: **30 recibieron 429**
(riesgo R-06). Los usuarios legítimos se bloqueaban entre sí sin haber fallado ni una contraseña.

Además, `X-Forwarded-For` se aceptaba siempre (riesgo R-14). Fuera de Render, cualquiera podía inventarse una IP
distinta en cada petición y saltarse todos los límites por IP.

## 2. Diseño nuevo

Todos los contadores usan la tabla `rate_limits` (persistente, compartida por todas las instancias, claves con hash)
y una ventana fija de 15 minutos. Si la base falla, se usa un contador en memoria: nunca se deja pasar sin límite.

| Capa | Qué cuenta | Límite | Para qué |
| --- | --- | --- | --- |
| 1. Tope por IP | Todos los intentos | 300 / 15 min | Que nadie gaste la CPU del servidor en scrypt inundando el inicio de sesión |
| 2. Fallidos por IP | Intentos sin contraseña correcta | **20 / 15 min** | Fuerza bruta desde una IP (el mismo número que antes) |
| 3. Modo estricto | Fallidos en todo el sitio | Si pasan de 200 / 15 min, la capa 2 baja a **5** | Ataques repartidos entre muchas IP (*password spraying*) |
| 4. Por cuenta | Fallos de esa cuenta, desde cualquier IP | 5 → bloqueo de 15 min | Sin cambios. También para nombres que no existen (`lockname:`), para no revelar qué cuentas existen |

### Cómo se cuenta un fallo

Cada intento se apunta como fallido **antes** de comprobar la contraseña. Se descuenta solo cuando la contraseña es
correcta.

- Así ni siquiera 60 intentos simultáneos superan los 20 fallidos permitidos: no hay carrera entre «consultar» y
  «apuntar» (prueba `test_concurrent_guesses_never_exceed_failure_limit`).
- Acertar no devuelve intentos ya fallados: un atacante con una cuenta válida no puede «recargar» su cupo
  intercalando inicios de sesión buenos (`test_successful_logins_do_not_reset_failure_count`).
- Cuentan como fallo: usuario inexistente, contraseña incorrecta, código TOTP incorrecto y cuenta bloqueada.
- No cuentan como fallo: contraseña correcta con cuenta pendiente, rechazada o desactivada, ni la petición del
  código TOTP (contraseña correcta, falta el código).

### Por qué no se debilita la protección

- Un atacante desde una IP sigue teniendo como máximo **20 contraseñas probadas cada 15 minutos**, igual que antes.
  Antes su límite efectivo también era 20, porque todos sus intentos fallan.
- Contra una cuenta concreta sigue habiendo 5 intentos cada 15 minutos, venga de las IP que venga.
- Durante un ataque repartido, cada IP baja a 5 fallidos (antes 20): la protección es **más estricta** que antes.
- `test_login_ip_limit_persists` (20 fallos y luego 429 aunque la contraseña sea correcta y se borre la memoria)
  sigue pasando sin cambios.

## 3. `X-Forwarded-For` solo desde proxies autorizados

`server.client_ip(peer, xff)`:

1. Si la conexión **no** viene de un proxy autorizado, se usa su dirección real y el encabezado se ignora.
2. Si viene de uno autorizado:
   - con `*`, se usa el **último** valor, el que añade el proxy (los anteriores los escribe el cliente);
   - con una lista de redes, se recorre la cadena de derecha a izquierda saltando los proxies autorizados. La primera
     dirección que no es un proxy autorizado es el cliente.
3. Un valor que no es una IP corta la cadena y se usa la dirección de la conexión.

Configuración, en la variable `CRYPTO_RADAR_TRUSTED_PROXIES`:

| Entorno | Valor | Efecto |
| --- | --- | --- |
| Render (variable `RENDER` presente) y sin definir la variable | `*` implícito | Igual que hoy en producción: el contenedor de Render solo recibe tráfico a través de su proxy |
| Fuera de Render y sin definir la variable | ninguno | Se ignora `X-Forwarded-For` |
| Detrás de un proxy propio | p. ej. `10.0.0.0/8` | Solo ese proxy puede indicar la IP del cliente |

Pruebas:
- `test_forwarded_for_cannot_dodge_limit_without_trusted_proxy`: 21 intentos con una IP inventada distinta en cada
  uno, desde una conexión no autorizada. Todos cuentan para la IP real y el 21.º recibe 429.
- `test_forwarded_for_trusted_proxy_separates_clients`: con el proxy autorizado, dos clientes distintos detrás de él
  tienen contadores separados.
- `test_forwarded_for_ignored_from_untrusted_peer`: cadena, saltos de proxy y valores basura.

**Pendiente de comprobar en Render**: que la IP que aparece en el registro de actividad del panel sea la del usuario
y no una del proxy. Si fuera la del proxy, todos compartirían contador, como antes del arreglo F-04.

## 4. Resultados

Ver la sección 3 de `docs/AUDITORIA_ESTRES_INTEGRAL.md` para la repetición de la prueba de carga con IP compartida.

| Escenario | Antes | Después |
| --- | --- | --- |
| 30 usuarios distintos, contraseña correcta, misma IP, uno tras otro | 10 con 429 (*) | 30 de 30 entran |
| 16 a la vez desde la misma IP (= hilos del servidor) | — | 16 de 16 entran |
| 50 a la vez por HTTP desde una IP (`carga.py`, `IP_COMPARTIDA=1`) | 30 con 429 (medido) | 50 de 50 entran (medido, `estres/ip_compartida_despues.json`) |
| 25 por HTTP desde 127.0.0.1 | 5 con 429 (*) | 25 de 25 entran |
| 20 contraseñas falsas desde una IP y luego la buena | 429 | 429 (igual) |
| 60 contraseñas falsas a la vez desde una IP | — | como mucho 20 comprobadas |
| 5 fallos contra una cuenta desde 5 IP distintas | bloqueo | bloqueo (igual) |
| Ataque repartido: más de 200 fallos en el sitio | 20 por IP | 5 por IP |

(*) Deducido del límite anterior de 20 intentos por IP; la medición real antes del cambio es la de
`carga_ip_compartida.json` (30 de 50 con 429). La columna «Después» sale de las pruebas ejecutadas.

## 5. Límites que siguen afectando a una IP compartida

- **Más de 20 comprobaciones simultáneas desde una IP**: cada intento cuenta como fallido mientras se comprueba,
  así que las que pasan de 20 reciben 429 aunque la contraseña sea buena. Con el servidor real no ocurre, porque
  solo hay 16 hilos (`CRYPTO_RADAR_WORKERS`); el servidor avisa al arrancar si se configuran más hilos que
  `LOGIN_IP_FAILS`. Una versión de la prueba con 24 hilos directos lo demostró (1–4 respuestas 429).

- **Solicitar acceso**: 3 solicitudes por IP y hora, y 60 en total por hora (`req:{ip}`, `req:global`). En una
  oficina con más de 3 personas pidiendo acceso a la vez, la cuarta recibe 429 y debe esperar una hora. Para el
  piloto cerrado basta, porque el administrador puede crear las cuentas desde el panel («Crear usuario»).
- **Fallos compartidos**: detrás de la misma IP, los 20 fallidos se reparten entre todos. Un compañero que se
  equivoca muchas veces, o un atacante en la misma red del operador, puede dejar sin cupo a los demás durante
  15 minutos. Es el precio de no debilitar el límite por IP. Con más usuarios, la mejora sería un desafío tipo
  Turnstile en lugar de un 429.
- **Bloqueo dirigido de una cuenta**: cualquiera que conozca un nombre de usuario puede bloquearlo 15 minutos con
  5 contraseñas falsas. Ya ocurría antes; se mantiene porque cambiarlo debilitaría la protección por cuenta.
