"""Las 23 configuraciones pre-registradas (research/edge/PREREGISTRO.md §3).

Cada estrategia define, con datos hasta el cierre de D:
  entry  : DataFrame bool (fecha × símbolo) candidatos a comprar en D+1
  score  : DataFrame float para ordenar candidatos
  exit_sig: DataFrame bool, salida a la apertura de D+1
  stop   : ('atr', k) stop inicial k·ATR; trail = k o None (trailing k·ATR sobre el cierre)
  weekly : True = entradas y salidas por señal solo el lunes (rebalanceo semanal); los stops son diarios
  sizing : 'risk' (0,5 % por operación) o 'vol' (objetivo de volatilidad 40 % anual)
  max_days: salida por tiempo
"""
from dataclasses import dataclass, field
import pandas as pd


@dataclass
class Strategy:
    name: str
    family: str
    params: dict
    entry: object = None
    score: object = None
    exit_sig: object = None
    stop_atr: float = 3.0
    trail_atr: float = None
    weekly: bool = False
    sizing: str = "risk"
    max_days: int = None
    rank_keep: int = None          # rebalanceo: se mantiene mientras siga en el top rank_keep
    crash_exit: bool = False


def _rank(score, cand):
    return score.where(cand).rank(axis=1, ascending=False, method="first")


def build_all(P, F, U):
    c = P["c"]
    out = []
    btc_up = F["btc_wk20"] == 1
    # A y D: momentum de serie temporal
    for L in (28, 56, 84):
        mom = (F[f"ret{L}"] > 0) & (c > F[f"sma{L}"]) & U
        sc = F[f"ret{L}"] / F["vol28"]
        for bf in (True, False):
            cand = mom & btc_up.values[:, None] if bf else mom
            rk = _rank(sc, cand)
            out.append(Strategy(f"A_tsmom_L{L}_btcf{int(bf)}", "A", {"L": L, "btc_filter": bf},
                                entry=rk <= 5, score=sc, exit_sig=~((rk <= 10) & cand), weekly=True, rank_keep=10))
        cand = mom
        rk = _rank(sc, cand)
        out.append(Strategy(f"D_volmom_L{L}", "D", {"L": L}, entry=rk <= 5, score=sc, exit_sig=~((rk <= 10) & cand),
                            weekly=True, sizing="vol", rank_keep=10, crash_exit=True))
    # B: Donchian
    for N, M in ((20, 10), (55, 27), (90, 45)):
        brk = (c > F[f"hi{N}"]) & U
        sc = c / F[f"hi{N}"] - 1
        out.append(Strategy(f"B_donchian_N{N}_exitchan", "B", {"N": N, "exit": "channel"},
                            entry=brk, score=-F["vol28"], exit_sig=c < F[f"lo{M}"]))
        out.append(Strategy(f"B_donchian_N{N}_trail3", "B", {"N": N, "exit": "atr3"},
                            entry=brk, score=-F["vol28"], exit_sig=pd.DataFrame(False, index=c.index, columns=c.columns),
                            trail_atr=3.0))
    # C: early breakout
    nofalse = pd.DataFrame(False, index=c.index, columns=c.columns)
    for p in (0.20, 0.35):
        comp = (F["bbw_pct"] <= p).astype(float).rolling(10, min_periods=1).max() > 0
        sig = comp & (F["vratio"] >= 1.2) & (c > F["hi55"]) & (F["rs28"] > 0) & U
        sc = F["rs28"]
        out.append(Strategy(f"C_early_p{int(p*100)}_trail3", "C", {"p": p, "exit": "atr3"},
                            entry=sig, score=sc, exit_sig=nofalse, trail_atr=3.0))
        out.append(Strategy(f"C_early_p{int(p*100)}_time30", "C", {"p": p, "exit": "time30"},
                            entry=sig, score=sc, exit_sig=nofalse, max_days=30))
    # E: híbrida
    comp35 = (F["bbw_pct"] <= 0.35).astype(float).rolling(10, min_periods=1).max() > 0
    for N in (20, 55):
        sig = (F["wk_above10"] == 1) & btc_up.values[:, None] & comp35 & (c > F[f"hi{N}"]) & (F["rs28"] > 0) & U
        for k in (2.5, 3.5):
            out.append(Strategy(f"E_hybrid_N{N}_trail{k}", "E", {"N": N, "trail": k},
                                entry=sig, score=F["rs28"], exit_sig=nofalse, stop_atr=k, trail_atr=k))
    return out
