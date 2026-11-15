# Pendientes y riesgos conocidos

Estado al 2026-11-15. **El proyecto no está terminado**: quedan puntos críticos.

## Críticos

| # | Pendiente | Por qué importa | Qué hace falta |
| --- | --- | --- | --- |
| 1 | La estrategia no supera la validación fuera de muestra (−18,6 % en 2024-2026, walk-forward −29,4 %). La investigación pre-registrada de 23 estrategias clásicas tampoco encontró ventaja (`research/edge/INFORME_VENTAJA.md`) | Las señales de compra no tienen ventaja demostrada | No operar con estas señales; si se sigue investigando, paper trading hacia adelante; no vender con cifras de rentabilidad |
| 2 | Pesos del puntaje sin validación estadística (correlación de rango negativa dentro y fuera de muestra) | El orden del ranking no anticipa mejores resultados | Rediseñar o reponderar las familias y validarlo en un periodo nuevo |
| 3 | Sin verificación de correo ni recuperación de contraseña | Quien registre primero el correo de administrador obtiene control total; un usuario que olvida la clave pierde la cuenta | Enviar correos (proveedor SMTP o API) con enlace firmado. Mientras tanto, registrar el administrador justo al desplegar |
| 4 | Pagos sin probar con un comercio real | El código verifica firmas y reconsulta la API, pero solo se probó con respuestas simuladas | Cuenta de comercio Wompi y NOWPayments, claves de sandbox y un pago de prueba de cada uno |

## Importantes

| # | Pendiente | Detalle |
| --- | --- | --- |
| 5 | Cobro recurrente no automático | Cada pago da 30 o 365 días; al vencer, el plan vuelve a Libre y el usuario paga otra vez. Falta suscripción con cargo automático |
| 6 | Sesgo de supervivencia residual en el backtest | Faltan las monedas que Binance borró por completo de la API |
| 7 | Sin facturación electrónica ni términos y condiciones legales revisados | Necesario para cobrar en Colombia |
| 8 | El repositorio es público | La estrategia y el código de pagos son visibles (AUDIT_REPORT X7). Pasarlo a privado es decisión del dueño |
| 9 | Datos on-chain y de ballenas | No hay fuente gratuita verificable: se muestran como N/D |
| 10 | El planificador duerme 20 min tras un escaneo fallido | También retrasa la vigilancia de precio en ese lapso (AUDIT_REPORT O4) |
| 11 | Límites de intentos en memoria | Se reinician al reiniciar el servicio y no se comparten entre varias instancias |
| 12 | Cifras de memecoins en la web de ventas | La prueba "a ciegas" se miró antes del ajuste final; la tarjeta lo advierte, pero no es una validación limpia |
