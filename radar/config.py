"""Configuración. Los valores del usuario se guardan en data/settings.json y se editan desde el panel."""
from __future__ import annotations
import json
import os
from pathlib import Path

ROOT = Path(os.environ.get("CRYPTO_RADAR_HOME", Path(__file__).resolve().parent.parent))
DATA_DIR = Path(os.environ.get("CRYPTO_RADAR_DATA", ROOT / "data"))
WEB_DIR = ROOT / "web"
DATA_DIR.mkdir(parents=True, exist_ok=True)
SETTINGS_FILE = DATA_DIR / "settings.json"

# Pesos de la puntuación (suman 100). Si un bloque no tiene datos verificables
# se marca N/D y su peso se reparte entre los bloques con datos (nunca se inventa).
SCORING = {
    "technical_structure": 20,
    "volume_and_liquidity": 15,
    "on_chain_activity": 15,
    "fundamentals_and_tokenomics": 15,
    "market_catalysts": 15,
    "risk_reward_ratio": 10,
    "market_sentiment": 10,
}

CLASSIFICATION = [
    (90, "OPORTUNIDAD EXCEPCIONAL"),
    (80, "OPORTUNIDAD DE ALTA CALIDAD"),
    (70, "OPORTUNIDAD INTERESANTE"),
    (60, "WATCHLIST"),
    (0, "RECHAZAR"),
]

# Categorías CoinGecko usadas para etiquetar los activos.
CATEGORIES = {
    "IA": "artificial-intelligence",
    "DEPIN": "depin",
    "RWA": "real-world-assets-rwa",
    "DEFI": "decentralized-finance-defi",
    "GAMING": "gaming",
    "INFRAESTRUCTURA": "layer-1",
    "MEMECOINS": "meme-token",
}

STABLES = {
    "usdt", "usdc", "dai", "fdusd", "tusd", "usde", "usds", "pyusd", "usdd", "busd", "eurc", "usd1",
    "frax", "lusd", "gusd", "usdp", "susde", "rlusd", "usdx", "usdb", "usd0", "bfusd", "usdtb", "usdf",
    "eur", "xaut", "paxg", "wbtc", "weth", "steth", "wsteth", "cbbtc", "weeth", "reth", "wbeth",
    "lbtc", "solvbtc", "bnsol", "jitosol", "msol", "ezeth", "rseth", "meth", "tbtc", "clbtc",
}

DEFAULTS = {
    "scan_every_hours": 4,
    "universe_size": 150,          # top N por capitalización a analizar
    "min_volume_usd": 5_000_000,   # liquidez mínima 24h
    "min_mcap_usd": 30_000_000,
    "quote": "USDT",
    "capital_usd": 1000,           # capital para calcular tamaño de posición
    "risk_per_trade_pct": 1.0,     # % del capital arriesgado por operación
    "max_position_pct": 20.0,      # máximo por activo
    "min_risk_reward": 3.0,
    "include_memecoins": True,
    "exclude": [],                 # símbolos a excluir siempre
    "watchlist": [],               # símbolos a vigilar aunque estén fuera del top
    "catalysts": {},               # {"SYMBOL": "texto del catalizador verificable"} -> puntúa catalizadores
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "desktop_notifications": True,
    "port": int(os.environ.get("PORT", 8777)),
}


def load_settings() -> dict:
    s = dict(DEFAULTS)
    if SETTINGS_FILE.exists():
        try:
            s.update(json.loads(SETTINGS_FILE.read_text("utf-8")))
        except Exception:
            pass
    return s


def save_settings(new: dict) -> dict:
    s = load_settings()
    for k, v in new.items():
        if k in DEFAULTS:
            default = DEFAULTS[k]
            try:
                if isinstance(default, bool):
                    v = v if isinstance(v, bool) else str(v).lower() in ("1", "true", "si", "sí", "on")
                elif isinstance(default, int) and not isinstance(default, bool):
                    v = int(float(v))
                elif isinstance(default, float):
                    v = float(v)
                elif isinstance(default, list):
                    if isinstance(v, str):
                        v = [x.strip().upper() for x in v.replace("\n", ",").split(",") if x.strip()]
                    else:
                        v = [str(x).strip().upper() for x in v]
                elif isinstance(default, dict):
                    v = {str(a).upper(): str(b) for a, b in dict(v).items() if str(b).strip()}
                else:
                    v = str(v).strip()
            except (TypeError, ValueError):
                continue
            s[k] = v
    SETTINGS_FILE.write_text(json.dumps(s, indent=2, ensure_ascii=False), "utf-8")
    return s


def classify(score: float) -> str:
    for th, name in CLASSIFICATION:
        if score >= th:
            return name
    return "RECHAZAR"
