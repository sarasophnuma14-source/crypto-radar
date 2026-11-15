# TEST_REPORT — Crypto Radar 2.0

Fecha de ejecución: 2026-11-15 · Rama `claude/project-thread-i8udp5` · Python 3.13 · PostgreSQL 16.15 local para T17.

## Resultado

```
$ TEST_DATABASE_URL=postgresql://radar@127.0.0.1:55432/radar python3 tests/test_suite.py -v
...
Ran 157 tests in 7.363s

OK
```

**157 pruebas ejecutadas, 157 aprobadas, 0 fallidas, 0 omitidas.** Todas usan datos sintéticos generados en la propia prueba
(sin red ni datos de mercado reales), así que son reproducibles. La prueba T17 (PostgreSQL de extremo a extremo) solo corre
si se define `TEST_DATABASE_URL`; sin esa variable se omite y el total aprobado es 156.

Cómo repetirlo:

```
python3 tests/test_suite.py -v                                   # 156 pruebas (SQLite)
TEST_DATABASE_URL=postgresql://usuario@host/db python3 tests/test_suite.py -v   # 157, incluye PostgreSQL
```

Además se ejecutaron los scripts de humo existentes `tests/run_fake.py` y `tests/run_portfolio_fake.py` (mercado simulado
de extremo a extremo): ambos terminan sin errores.

## Qué cubre cada bloque

| Bloque | Pruebas | Qué verifica |
| --- | --- | --- |
| T01 Datos | 10 | Vela abierta descartada, huecos, OHLC incoherente, datos viejos, historial corto, bloqueo de señal con mala calidad |
| T02 Causalidad | 6 | Indicadores y decisiones idénticos con la serie completa o truncada (sin mirar al futuro), pivotes solo tras confirmarse |
| T03 Early Entry | 14 | Ruptura con volumen, rechazo en tendencia bajista o sin liquidez, lateral sin volumen no es acumulación, sobreextensión, pesos de la especificación que suman 100, redistribución si falta una familia, score acotado |
| T04 Manipulación | 9 | Pump and dump, subida vertical sin liquidez, spread amplio, libro N/D sin datos, riesgo alto bloquea la entrada, cada punto con evidencia, nunca afirma "prueba" |
| T05 Salidas | 8 | Decisiones válidas, una señal débil sola nunca cierra, el stop nunca baja, stop a la entrada con beneficio, parciales configurables |
| T06 Régimen | 9 | BULLISH / NEUTRAL / BEARISH / HIGH VOLATILITY / CAPITULATION y su efecto en tamaño, puntaje mínimo y fases permitidas |
| T07 Plan | 6 | Zona de entrada no por encima del precio, stop bajo la entrada con distancia mínima en ATR, TP ordenados y múltiplos de R, tope por posición |
| T08 Portfolio | 12 | Tamaño por riesgo, límites por activo, categoría, número de posiciones, correlación, riesgo abierto, freno por drawdown |
| T09 Métricas | 7 | Profit factor y acierto (N/D sin pérdidas), signo del Sharpe, drawdown máximo, CAGR, comparativa, desgloses |
| T10 Backtest | 19 | Llenado de órdenes límite y stop-buy, stop el mismo día, huecos, parciales, costes, expiración, universo por fecha, pausa por drawdown no permanente |
| T11 Almacén y alertas | 8 | Escrituras atómicas entre hilos, deduplicación de alertas (también en paralelo), textos sin promesas de rentabilidad, resumen diario una sola vez |
| T12 Escáner | 8 | Escaneo completo con mercado simulado, secciones del informe, régimen, ranking ordenado que prefiere fases tempranas y excluye sobreextendidas |
| T13 SaaS | 23 | Registro, contraseñas débiles, correo duplicado, bloqueo de cuenta, límite por IP, CSRF, origen ajeno, POST no JSON, cuerpo > 64 KB, cookie HttpOnly, cabeceras de seguridad, hash scrypt con sal, token de sesión guardado con hash, cierre de sesión, plan vencido vuelve a Libre, aislamiento entre usuarios, límites del plan Libre, permisos de administrador |
| T14 Pagos | 9 | Firma de integridad Wompi, webhook con firma inválida, monto distinto, transacción rechazada, API caída (no se concede nada), concesión solo tras confirmar con la API, idempotencia, firma de NOWPayments, concesión manual solo de administrador con motivo |
| T15 Telegram y memecoins | 5 | Vinculación por código, código inválido, comandos sin vincular, perfil de riesgo de memecoins, on-chain N/D |
| T16 Interfaz | 3 | Las 11 secciones existen, sintaxis de `app.js` válida, la vista de backtest no tiene cifras escritas a mano |
| T17 PostgreSQL | 1 | Esquema, registro, inicio de sesión, almacén `kv` y cartera sobre PostgreSQL real |

## Fallos encontrados por la batería y cómo se resolvieron

La primera ejecución dio **28 problemas** (4 fallos y 24 errores). No se ocultó ninguno; cada uno se clasificó como fallo real
del código o error de la prueba:

| Problema | Tipo | Resolución |
| --- | --- | --- |
| Con PostgreSQL en codificación SQL_ASCII el driver devolvía bytes en lugar de texto: el inicio de sesión fallaba siempre | **Fallo real** | `radar/db.py` fuerza `client_encoding = UTF8` al conectar |
| Datos con 10 días de retraso seguían marcados como `ok` (la penalización no bastaba para bajar del umbral) | **Fallo real** | `radar/quant/quality.py`: datos desactualizados nunca son `ok` |
| `random.randint(0, 1e9)` en el ayudante de registro | Error de la prueba | `10**9` (causaba 24 errores en cascada) |
| El límite de 5 registros por IP y hora bloqueaba las pruebas siguientes | Error de la prueba (el límite funciona) | Se limpia el contador en cada prueba y se añadió una prueba explícita del límite |
| La prueba de pivotes esperaba `None` al final, pero la lista arrastra el último pivote confirmado | Error de la prueba | Ahora comprueba que un máximo en la vela 198 aún no aparece como pivote |
| La prueba del universo por fecha tenía la aserción invertida | Error de la prueba | Corregida: el día 130 la moneda con más volumen reciente encabeza el universo |

## Lo que estas pruebas NO demuestran

- Que la estrategia gane dinero. Eso lo mide el backtest (ver `BACKTEST_REPORT.md`) y **hoy no supera la validación fuera de muestra**.
- Pagos reales: Wompi y NOWPayments se probaron con respuestas simuladas de su API y firmas calculadas con claves de prueba.
  Falta una transacción real en el sandbox de cada proveedor con las claves del comercio.
- El bot de Telegram contra la API real de Telegram (se probó la lógica con un transporte simulado).
- Carga y concurrencia de muchos usuarios a la vez.

## Lista completa de pruebas ejecutadas

### T01_Datos (10 pruebas)

- `test_bad_quality_rejects_signal`: ok
- `test_drop_open_candle_keeps_closed`: ok
- `test_drop_open_candle_removes_unclosed`: ok
- `test_quality_clean_series_ok`: ok
- `test_quality_detects_bad_ohlc`: ok
- `test_quality_detects_duplicates`: ok
- `test_quality_detects_gaps`: ok
- `test_quality_detects_stale`: ok
- `test_quality_short_history`: ok
- `test_quality_zero_volume`: ok

### T02_Causalidad (6 pruebas)

- `test_backtest_signal_uses_only_past`: ok
- `test_engine_same_output_full_vs_truncated`: ok
- `test_hh20_prev_excludes_current_bar`: ok
- `test_indicators_identical_when_future_removed`: ok
- `test_pivots_only_after_confirmation`: ok
- `test_vol_avg_prev_excludes_current_bar`: ok

### T03_Early (14 pruebas)

- `test_breakout_with_volume`: ok
- `test_custom_weights_change_score`: ok
- `test_downtrend_rejected`: ok
- `test_families_have_evidence_lists`: ok
- `test_flat_price_without_volume_is_not_accumulation`: ok
- `test_illiquid_rejected`: ok
- `test_missing_family_redistributes_weight`: ok
- `test_overextended_detected`: ok
- `test_overextension_penalizes_score`: ok
- `test_phase_in_allowed_set`: ok
- `test_rejected_score_capped_40`: ok
- `test_score_in_range`: ok
- `test_weights_match_spec`: ok
- `test_weights_sum_100`: ok

### T04_Manipulacion (9 pruebas)

- `test_book_nd_without_book`: ok
- `test_clean_series_low_risk`: ok
- `test_every_point_has_evidence_text`: ok
- `test_high_risk_blocks_entry`: ok
- `test_note_never_claims_proof`: ok
- `test_pump_and_dump_detected`: ok
- `test_risk_bounded`: ok
- `test_vertical_move_without_liquidity`: ok
- `test_wide_spread_adds_risk`: ok

### T05_Salidas (8 pruebas)

- `test_close_at_stop`: ok
- `test_decision_values`: ok
- `test_downtrend_triggers_exit_evidence`: ok
- `test_hold_without_signals`: ok
- `test_partials_configurable`: ok
- `test_single_weak_signal_never_closes`: ok
- `test_stop_never_lowered`: ok
- `test_stop_to_breakeven_after_profit`: ok

### T06_Regimen (9 pruebas)

- `test_bearish`: ok
- `test_bullish`: ok
- `test_capitulation`: ok
- `test_high_volatility`: ok
- `test_neutral_mixed`: ok
- `test_policy_tightens_with_risk`: ok
- `test_regime_affects_size`: ok
- `test_regime_blocks_phase`: ok
- `test_regime_min_score`: ok

### T07_Plan (6 pruebas)

- `test_entry_zone_not_above_price`: ok
- `test_min_stop_distance_atr`: ok
- `test_position_capped_by_max_pct`: ok
- `test_stop_below_entry`: ok
- `test_targets_ordered`: ok
- `test_tp_multiples_of_R`: ok

### T08_Portfolio (12 pruebas)

- `test_alt_exposure_cap`: ok
- `test_cash_cap`: ok
- `test_correlation_function`: ok
- `test_correlation_rejects`: ok
- `test_drawdown_halves_size`: ok
- `test_drawdown_stop_blocks`: ok
- `test_invalid_stop_rejected`: ok
- `test_liquidity_cap`: ok
- `test_max_position_cap`: ok
- `test_max_positions`: ok
- `test_open_risk_cap`: ok
- `test_risk_based_size`: ok

### T09_Metricas (7 pruebas)

- `test_benchmark`: ok
- `test_breakdowns`: ok
- `test_cagr`: ok
- `test_max_drawdown`: ok
- `test_profit_factor_and_win_rate`: ok
- `test_profit_factor_none_without_losses`: ok
- `test_sharpe_sign`: ok

### T10_Backtest (19 pruebas)

- `test_all_targets`: ok
- `test_ambiguous_bar_stop_first`: ok
- `test_benchmark_present`: ok
- `test_breakout_stop_order`: ok
- `test_cash_accounting_consistent`: ok
- `test_drawdown_pause_not_permanent`: ok
- `test_end_of_period_closes_positions`: ok
- `test_fees_charged`: ok
- `test_fill_next_day_at_open_or_limit`: ok
- `test_gap_below_stop_fills_at_open`: ok
- `test_limit_not_filled_if_price_above`: ok
- `test_no_fill_on_signal_day`: ok
- `test_order_expires`: ok
- `test_partial_tp1_moves_stop_to_entry`: ok
- `test_same_day_stop_pessimistic`: ok
- `test_score_validation_structure`: ok
- `test_stop_hit_after_entry`: ok
- `test_trade_log_has_fills`: ok
- `test_universe_point_in_time`: ok

### T11_AlmacenAlertas (8 pruebas)

- `test_alert_dedupe`: ok
- `test_alert_dedupe_parallel`: ok
- `test_alert_has_no_return_promise`: ok
- `test_exit_text`: ok
- `test_signal_alert_content`: ok
- `test_storage_roundtrip`: ok
- `test_storage_update_atomic_under_threads`: ok
- `test_summaries_once_per_day`: ok

### T12_Escaner (8 pruebas)

- `test_rank_penalizes_runup`: ok
- `test_rank_prefers_early_phase`: ok
- `test_ranking_excludes_overextended`: ok
- `test_ranking_fields`: ok
- `test_ranking_sorted`: ok
- `test_regime_in_report`: ok
- `test_report_sections`: ok
- `test_scan_completes`: ok

### T13_SaaS (23 pruebas)

- `test_account_lockout`: ok
- `test_activity_log`: ok
- `test_admin_email_gets_admin`: ok
- `test_body_too_large`: ok
- `test_checkout_disabled_without_keys`: ok
- `test_csrf_required`: ok
- `test_duplicate_email`: ok
- `test_expired_plan_is_free`: ok
- `test_foreign_origin_blocked`: ok
- `test_free_plan_limits`: ok
- `test_invalid_email_rejected`: ok
- `test_logout_invalidates_session`: ok
- `test_non_admin_cannot_scan_or_change_system_settings`: ok
- `test_non_json_post_blocked`: ok
- `test_password_hash_scrypt_salted`: ok
- `test_position_input_validation`: ok
- `test_registration_rate_limited_per_ip`: ok
- `test_requires_login`: ok
- `test_security_headers`: ok
- `test_session_cookie_flags`: ok
- `test_session_token_stored_hashed`: ok
- `test_user_isolation_positions`: ok
- `test_weak_password_rejected`: ok

### T14_Pagos (9 pruebas)

- `test_admin_grant_requires_admin_and_reason`: ok
- `test_amount_mismatch_rejected`: ok
- `test_api_unreachable_no_grant`: ok
- `test_bad_signature_rejected`: ok
- `test_checkout_integrity_signature`: ok
- `test_declined_not_granted`: ok
- `test_idempotent_grant`: ok
- `test_nowpayments_signature`: ok
- `test_valid_webhook_grants_after_api_confirmation`: ok

### T15_TelegramMemes (5 pruebas)

- `test_commands_without_link`: ok
- `test_invalid_code`: ok
- `test_link_flow`: ok
- `test_meme_onchain_nd`: ok
- `test_meme_risk_profile`: ok

### T16_Interfaz (3 pruebas)

- `test_eleven_sections`: ok
- `test_js_syntax`: ok
- `test_no_hardcoded_numbers_in_backtest_view`: ok

### T17_Postgres (1 pruebas)

- `test_postgres_end_to_end`: ok
