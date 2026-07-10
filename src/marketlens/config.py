"""Configuration loading.

All tunable assumptions (date window, inclusion policy, fees, rate limits)
live in config.yaml at the repo root. Code reads them from here so there are
no magic constants inline.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel


class IngestionConfig(BaseModel):
    since: str
    until: str
    min_lifetime_hours: float = 24
    price_fidelity_minutes: int = 1440
    price_sample_size: int = 15000
    sample_seed: int = 42


class StorageConfig(BaseModel):
    db_path: str = "data/marketlens.sqlite"
    raw_dir: str = "data/raw"


class HttpConfig(BaseModel):
    user_agent: str
    timeout_seconds: float = 30
    max_retries: int = 6
    backoff_base_seconds: float = 1.0
    backoff_factor: float = 2.0
    requests_per_second: float = 4


class PolymarketConfig(BaseModel):
    gamma_base_url: str
    clob_base_url: str
    page_size: int = 100
    metadata_min_volume: float = 1000


class KalshiConfig(BaseModel):
    base_url: str
    page_size: int = 1000
    skip_frequencies: list[str] = []
    skip_ticker_prefixes: list[str] = []
    skip_categories: list[str] = []


class Config(BaseModel):
    ingestion: IngestionConfig
    storage: StorageConfig
    http: HttpConfig
    polymarket: PolymarketConfig
    kalshi: KalshiConfig
    # Fee and backtest sections are consumed in later phases; kept as raw
    # dicts so this model does not need to change when they gain fields.
    fees: dict = {}
    backtest: dict = {}

    # Directory that relative storage paths resolve against.
    root: Path = Path(".")

    def db_path(self) -> Path:
        return self.root / self.storage.db_path

    def raw_dir(self) -> Path:
        return self.root / self.storage.raw_dir


def load_config(path: str | os.PathLike | None = None) -> Config:
    """Load config.yaml. Defaults to MARKETLENS_CONFIG or ./config.yaml."""
    cfg_path = Path(path or os.environ.get("MARKETLENS_CONFIG", "config.yaml"))
    with open(cfg_path) as f:
        raw = yaml.safe_load(f)
    cfg = Config(**raw)
    cfg.root = cfg_path.resolve().parent
    return cfg
