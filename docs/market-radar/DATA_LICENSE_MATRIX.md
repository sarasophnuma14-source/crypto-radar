# Matriz de licencias de datos · Market Radar

Fecha: 18-nov-2026. Fuente de cada celda: `DATA_PROVIDER_RESEARCH.md`.
Leyenda: **Sí** = verificado en página oficial · **No** = verificado que no · **?** = NO VERIFICADO · **Contrato** = depende de un acuerdo aparte.

> Esta matriz **no es asesoría legal**. Sirve para saber qué preguntar y qué bloquea cada mercado. Ningún proveedor puede activarse en producción hasta que su fila tenga "Sí" en las columnas que usa Market Radar y exista el documento firmado o la aceptación de términos archivada (`provider_licenses.contract_ref`).

## 1. Usos que necesita Market Radar

| Código | Uso |
|---|---|
| ALM | Almacenar velas en nuestra base |
| VIS | Mostrar precios a usuarios de pago (terceros) |
| DER | Mostrar datos derivados (indicadores, score, estados) |
| ALT | Enviar alertas con datos por Telegram |
| EXP | Permitir exportar a los usuarios |
| INV | Usar los datos para investigación interna |
| STG | Usarlos en staging con testers |

## 2. Matriz

| Proveedor · plan | Mercados | ALM | VIS | DER | ALT | EXP | INV | STG | Atribución | Costo público | Bloqueo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| CoinGecko · Demo (sin clave) | Cripto | ? | **No** (no comercial) | **No** | **No** | **No** | ? | ? | Sí | 0 | No sirve para cobrar |
| CoinGecko · Basic | Cripto | ? | Sí (comercial) | ? | ? | ? | Sí | ? | **Obligatoria** | US$35/mes | Verificar límite de llamadas y alcance |
| Binance API pública | Cripto | ? | ? | ? | ? | ? | ? | ? | ? | 0 | Sin política oficial publicada |
| data.binance.vision | Cripto (histórico) | ? | ? | ? | ? | ? | ? | ? | ? | 0 | Leer su PDF de términos |
| Bybit / OKX / Coinbase / Kraken | Cripto | ? | ? | ? | ? | ? | ? | ? | ? | 0 | Sin revisar |
| Massive · Individual | Acciones, FX, cripto | ? | **No** | **No** | **No** | **No** | Sí (personal) | **No** | ? | US$29–199/mes | Personal |
| Massive · Business | Acciones / FX / opciones | ? | **Sí** | ? | ? | ? | ? | **Sí** (requerido para testers) | ? | Stocks US$2.499, FX US$999 | Precio |
| Twelve Data · Basic | Acciones, ETF, FX, cripto | ? | **No** ("internal non-display") | **No** | **No** | **No** | Sí | ? | — | 0 | Interno |
| Twelve Data · Grow/Pro/Ultra | Igual | ? | **No** | **No** | **No** | **No** | Sí | ? | — | — | Personal/interno |
| Twelve Data · Venture | Acciones y ETF EE. UU./UE, EOD global, materias primas | ? | **Sí** (external display) | Sí con atribución | ? | ? | Sí | ? | **Obligatoria** para derivados públicos | US$499/mes | Datos no EE. UU. requieren aprobación extra; FX/cripto/índices sin confirmar |
| Twelve Data · Enterprise | + ETF metrics | ? | Sí | Sí | ? | ? | Sí | ? | Obligatoria | US$1.099/mes | Precio |
| Tiingo | Acciones, FX, cripto, noticias | ? | **No** (interno) | ? | ? | ? | Sí | ? | ? | US$30–50/mes | Redistribución aparte (SECUNDARIO) |
| FMP | Acciones, fundamentales | ? | **Contrato** (Display Agreement) | Contrato | ? | ? | ? | ? | ? | ? | Contrato |
| EODHD · comercial | Global | ? | ? | ? | ? | ? | ? | ? | ? | Cotización | Cotización; reporta usuarios a bolsas |
| Databento · CME | Futuros CME | ? | ? | ? | ? | ? | ? | ? | ? | desde US$179/mes + CME | Display y tarifas CME |
| S&P DJI | Índices S&P/Dow | ? | **Contrato** (licencian a medios) | ? | ? | ? | ? | ? | ? | ? | Contrato |
| Otros índices (Nasdaq, FTSE, STOXX, Nikkei) | Índices | ? | ? | ? | ? | ? | ? | ? | ? | ? | Sin revisar |
| FRED | Macro | ? | Sí (salvo series con copyright) | Sí | ? | ? | Sí | Sí | **Aviso obligatorio** | 0 | Series de terceros con permiso |
| EIA | Energía | ? | Sí | Sí | ? | ? | Sí | Sí | **Obligatoria** | 0 | — |
| CFTC COT | Posiciones futuros | ? | Probable | Probable | ? | ? | Sí | Sí | Recomendable | 0 | Confirmar política web |
| USDA | Agrícola | ? | Probable (dominio público) | Probable | ? | ? | Sí | Sí | Recomendable | 0 | Confirmar |
| Benzinga vía Massive | Noticias | ? | Hereda plan base | ? | ? | ? | ? | ? | ? | +US$99/mes | Plan base Business |

## 3. Estado por mercado de la especificación

| Universo | Fuente candidata | ¿Licencia de visualización confirmada? | Puede habilitarse |
|---|---|---|---|
| Criptomonedas | CoinGecko Basic + exchange por confirmar | Parcial (CoinGecko sí, velas de exchange no) | **No** |
| Acciones | Twelve Data Venture | Sí en principio; faltan tarifas de bolsa y alcance | **No** |
| ETF | Twelve Data Venture | Igual | **No** |
| Forex | Massive Currencies / Twelve Data | Massive sí (US$999); Twelve Data sin confirmar | **No** |
| Oro y plata | Spot OTC / futuros / ETF | ETF sí con proveedor de acciones; spot y futuros no | **No** |
| Índices | ETF proxy o licencia del índice | Proxy sí con proveedor de ETF; índice no | **No** |
| Petróleo y gas | Databento CME + EIA | EIA sí (contexto); precios no | **No** |
| Agrícolas | CME/ICE + USDA | USDA probable (contexto); precios no | **No** |

**Ningún mercado nuevo cumple hoy el criterio 2 de la §18 ("licencia aplicable confirmada").** Esto es esperado en Fase 1 y es el principal camino crítico del roadmap.

## 4. Reglas que el código hará cumplir

1. `provider_licenses` es la fuente de verdad; el código no asume derechos.
2. Sin `allows_display` vigente: la API devuelve `license_display:false` y la interfaz muestra "Dato no disponible por licencia".
3. Sin `allows_storage`: el adaptador trabaja en memoria y no escribe en `candles`.
4. `max_storage_days`: tarea diaria de borrado con registro en `audit_events`.
5. Atribución: el texto exacto de `requires_attribution` aparece junto a cada dato o gráfico.
6. Staging cuenta como visualización salvo que la licencia diga lo contrario.
7. Cambiar una fila de `provider_licenses` es acción de administrador con TOTP y queda en `audit_events` con hash encadenado.

## 5. Responsables

| Acción | Responsable |
|---|---|
| Pedir términos por escrito (preguntas en `DATA_PROVIDER_RESEARCH.md` §11) | PATRON (Claude prepara los correos; no los envía) |
| Revisión legal de contratos | Abogado (no cotizado) |
| Registrar la licencia en `provider_licenses` | Administrador con TOTP |
| Contratar cualquier plan | **Solo PATRON, con autorización expresa** |
