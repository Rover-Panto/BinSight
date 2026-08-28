"""
BinSight Machine Learning & Overflow Forecasting Subsystem (`ml`).

Official forecasting provider package for the BinSight smart waste management platform.
Exposes public provider classes and utilities for real telemetry and simulation integration.
"""
from pathlib import Path

# Relative imports from src/
from .src.serve import ForecastProvider, OverflowRiskModel, FORECAST_HORIZONS
from .src.features import build_feature_table, FEATURE_COLUMNS
from .src.label import risk_level_from_hours, OVERFLOW_THRESHOLD_PCT

__version__ = "1.1.0"
__all__ = [
    "ForecastProvider",
    "OverflowRiskModel",
    "FORECAST_HORIZONS",
    "build_feature_table",
    "FEATURE_COLUMNS",
    "risk_level_from_hours",
    "OVERFLOW_THRESHOLD_PCT",
    "__version__",
]
