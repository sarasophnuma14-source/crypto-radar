# Decisión comercial GO / NO-GO · Crypto Radar 2.1

Fecha: 16 de noviembre de 2026.

**Alcance:** define con qué datos se autoriza **cobrar**. Es distinto de `GO_NO_GO_PILOTO.md`, que decide si se puede **abrir el piloto gratuito**.

## Veredicto hoy: **NO-GO comercial**

No es un juicio sobre el producto. Es que **no hay ningún dato de demanda**:

- el piloto no ha empezado;
- no hay retención medida;
- no hay intención de pago registrada;
- no hay licencia comercial de datos;
- no hay concepto fiscal;
- el texto legal está sin completar.

Un GO hoy sería una decisión sin evidencia.

## 1. Cómo se decide

La decisión pasa por **tres compuertas en orden**. Cada una necesita **evidencia ejecutada**, igual que el GO del piloto: una recomendación escrita no basta.

| Compuerta | Pregunta | Dónde se mide |
|---|---|---|
| **A. Requisitos** | ¿Se puede cobrar de forma legal, segura y honesta? | `REQUISITOS_LANZAMIENTO.md`: todos los bloqueantes cerrados |
| **B. Demanda** | ¿La gente usa el producto y dice que pagaría? | `PLAN_PILOTO_90_DIAS.md` §3, al día 60 o 90 |
| **C. Cohorte de pago controlada** | ¿Pagan de verdad, y se quedan? | Hasta 50 clientes de pago durante 60 días |

Solo después de **C** se abre la venta al público.

## 2. Compuerta B: criterios de demanda

Se leen sobre **30 o más usuarios activados**. Con menos, la decisión es **extender el piloto**, no GO.

| # | Criterio | Umbral GO | Zona gris (ajustar y repetir 30 días) | NO-GO |
|---|---|---|---|---|
| B1 | Activación | ≥ 50 % | 35 % a 49 % | < 35 % |
| B2 | Retención a 30 días (activados) | ≥ 35 % | 20 % a 34 % | < 20 % |
| B3 | Retención a 60 días | ≥ 25 % | 15 % a 24 % | < 15 % |
| B4 | Prueba de decepción: «muy decepcionado» | ≥ 40 % | 25 % a 39 % | < 25 % |
| B5 | Intención de pago a US$15 («seguro» + «probablemente») | ≥ 30 % de activos a 30 días | 15 % a 29 % | < 15 % |
| B6 | Lista de interés «avisarme cuando abra Pro a US$15» | ≥ 2 × punto de equilibrio con F cotizado (`UNIT_ECONOMICS.md` §7) | 1 a 2 × equilibrio | < 1 × equilibrio |
| B7 | Van Westendorp | El rango aceptable incluye US$15 | Rango por debajo de US$15: probar US$12 | Rango por debajo de US$8 |

**Regla de combinación:**

- **GO a la compuerta C** si B1, B2, B4 y B5 están en GO y **ninguno** de los siete está en NO-GO.
- **NO-GO** si B2 **o** B4 están en NO-GO. Son los criterios que mejor predicen retención real. Opciones en ese caso:
  - replantear la propuesta de valor;
  - volver a la investigación (sin tocar el holdout);
  - pausar el producto.
- **Zona gris** en cualquier otro caso. Se corrige lo que señalen las encuestas (UX, precio, contenido) y se mide de nuevo durante 30 días. Como máximo **una** extensión; después, la decisión es GO o NO-GO.

## 3. Compuerta C: cohorte de pago controlada

**Requiere** la autorización expresa de PATRON para activar pagos y la compuerta A cerrada.

**Diseño:**

- Hasta 50 clientes, invitados desde la lista de interés.
- Precio US$15 o US$149.
- Reembolso completo en los primeros 14 días, que **revoca el plan** (`REQUISITOS_LANZAMIENTO.md` R-09).
- Duración de 60 días.

| # | Criterio | Umbral para abrir al público |
|---|---|---|
| C1 | Conversión de la lista de interés a pago | ≥ 10 % de los invitados |
| C2 | Reembolsos en 14 días | ≤ 10 % de los cobros |
| C3 | Cancelación del mes 1 al mes 2 (mensuales) | ≤ 15 % |
| C4 | Incidentes de cobro: doble cobro, plan no otorgado, plan sin revocar | 0 sin resolver en 48 h |
| C5 | Contracargos | 0 |
| C6 | Costo real mensual (Neon, Render, CoinGecko, comisiones) | Dentro de ±25 % de `UNIT_ECONOMICS.md` |
| C7 | Contribución acumulada | Cubre los costos fijos conocidos del período |

Si C1, C2 o C3 fallan, se vuelve a la zona gris de B con los datos reales, que ahora pesan más que las encuestas.

## 4. Qué decisiones toma PATRON en cada punto

| Momento | Decisión | Opciones |
|---|---|---|
| Ahora | Autorizar la instrumentación del piloto y los arreglos P0 y P1 | Sí / no |
| Día 0 | Abrir el piloto | Solo si `GO_NO_GO_PILOTO.md` está en GO |
| Día 60 | Compuerta B | GO a C / extender 30 días / NO-GO |
| Tras B en GO | Activar pagos para la cohorte C | Sí / no (no es reversible para quien ya pagó) |
| Día 60 de C | Abrir al público | Sí / repetir con ajustes / no |
| Con los datos del día 60 | Élite | Construir los 2 diferenciadores con más demanda / seguir solo con Pro |

## 5. Qué nunca cambia el veredicto

- Que un período de mercado haga «verse bien» al ranking. No hay ventaja demostrada y eso no cambia con anécdotas.
- Comentarios positivos aislados sin las métricas del §2.
- La urgencia de lanzar antes de un ciclo alcista.
