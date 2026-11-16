"""Modelo de costes por exchange: comisiones, spread, deslizamiento, impacto de mercado, funding y latencia.

Las comisiones son las del nivel minorista más bajo publicadas por cada exchange; CAMBIAN con el tiempo y por región,
así que deben verificarse en la web del exchange antes de usarlas en una evaluación (cada hipótesis registra el modelo
de costes que usa). Valores en fracción (0.001 = 0,10 %).
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

# (maker, taker). Nivel base, sin descuentos por token ni volumen. Revisar antes de usar.
COMISIONES = {
    "binance_spot": (0.0010, 0.0010),
    "binance_um": (0.0002, 0.0005),
    "coinbase": (0.0040, 0.0060),        # Coinbase Advanced, nivel < 10 k USD/mes
    "kraken": (0.0025, 0.0040),          # Kraken Pro, nivel inicial
    "okx_spot": (0.0008, 0.0010),
    "okx_swap": (0.0002, 0.0005),
}
# Semiespread típico (fracción del mid) por clase de liquidez cuando no hay medición propia
SEMISPREAD_POR_NIVEL = {"btc_eth": 0.00005, "top10": 0.0002, "top50": 0.0008, "resto": 0.0025}


@dataclass
class ModeloCostes:
    exchange: str = "binance_spot"
    ejecucion: str = "taker"                  # taker | maker (maker exige modelar no-ejecución; por defecto taker)
    semispread: float | dict | None = None    # fijo, por símbolo o None ⇒ por nivel de liquidez
    nivel: dict = field(default_factory=dict) # símbolo -> clave de SEMISPREAD_POR_NIVEL
    deslizamiento: float = 0.0002             # adicional fijo por operación
    impacto_k: float = 0.5                    # impacto = k · σ_barra · sqrt(participación)
    participacion_max: float = 0.01           # fracción máxima del volumen de la barra
    latencia_barras: int = 1                  # se ejecuta en la apertura de la barra t+latencia
    multiplicador: float = 1.0                # 2.0 para la prueba de estrés de costes ×2

    def comision(self):
        mk, tk = COMISIONES[self.exchange]
        return (mk if self.ejecucion == "maker" else tk) * self.multiplicador

    def semi(self, symbol):
        if isinstance(self.semispread, (int, float)):
            s = float(self.semispread)
        elif isinstance(self.semispread, dict) and symbol in self.semispread:
            s = float(self.semispread[symbol])
        else:
            s = SEMISPREAD_POR_NIVEL[self.nivel.get(symbol, "resto")]
        return s * self.multiplicador

    def coste_unitario(self, symbol, notional, volumen_barra_notional, sigma_barra):
        """Coste total en fracción del notional operado (sin funding)."""
        part = notional / volumen_barra_notional if volumen_barra_notional and volumen_barra_notional > 0 else 1.0
        impacto = self.impacto_k * (sigma_barra if np.isfinite(sigma_barra) else 0.0) * math.sqrt(max(part, 0.0))
        return self.comision() + self.semi(symbol) + self.deslizamiento * self.multiplicador + impacto * self.multiplicador

    def desglose(self, symbol, notional, volumen_barra_notional, sigma_barra):
        part = notional / volumen_barra_notional if volumen_barra_notional and volumen_barra_notional > 0 else 1.0
        imp = self.impacto_k * (sigma_barra if np.isfinite(sigma_barra) else 0.0) * math.sqrt(max(part, 0.0))
        m = self.multiplicador
        return {"comision": self.comision() * notional, "spread": self.semi(symbol) * notional,
                "deslizamiento": self.deslizamiento * m * notional, "impacto": imp * m * notional}


def funding_pagado(posicion_notional: pd.DataFrame, tasas: pd.DataFrame):
    """Funding de perpetuos: un largo PAGA la tasa positiva y un corto la COBRA. posicion_notional con signo.
    Devuelve el coste (positivo = pago) por instante de liquidación."""
    t = tasas.reindex(posicion_notional.index).fillna(0.0)
    return (posicion_notional * t).sum(axis=1)


def coste_ida_vuelta(modelo: ModeloCostes, symbol="BTC", notional=10_000, vol_barra=1e9, sigma=0.01):
    """Coste de entrar y salir una vez, en fracción: útil para fijar el umbral de rentabilidad mínimo por operación."""
    return 2 * modelo.coste_unitario(symbol, notional, vol_barra, sigma)
