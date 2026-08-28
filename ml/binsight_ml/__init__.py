"""
binsight_ml — installable forecasting package for BinSight.

This module re-exports the runtime forecast provider so that after
``pip install -e ./ml`` (or a built wheel), consumers can do::

    from binsight_ml import ForecastProvider

The actual implementation lives in ``ml/src/``.  This thin wrapper
adjusts ``sys.path`` so that the same source works both as an in-repo
relative import and as an installed package.
"""
import importlib
import sys
from pathlib import Path

# Locate the src/ directory relative to this file.
_SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Import the runtime modules directly (not as relative imports)
from serve import ForecastProvider, OverflowRiskModel, FORECAST_HORIZONS  # noqa: E402
from features import build_feature_table, FEATURE_COLUMNS  # noqa: E402
from label import (  # noqa: E402
    risk_level_from_hours,
    OVERFLOW_THRESHOLD_PCT,
    SERVICE_THRESHOLD_PCT,
)

__version__ = "2.0.0"
__all__ = [
    "ForecastProvider",
    "OverflowRiskModel",
    "FORECAST_HORIZONS",
    "build_feature_table",
    "FEATURE_COLUMNS",
    "risk_level_from_hours",
    "OVERFLOW_THRESHOLD_PCT",
    "SERVICE_THRESHOLD_PCT",
    "__version__",
]
