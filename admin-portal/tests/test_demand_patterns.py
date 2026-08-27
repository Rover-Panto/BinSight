from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from binsight.config import load_config
from binsight.demand import (
    DemandEvent,
    DemandScenario,
    cyclic_month_factor,
    deterministic_seasonal_factor,
    event_effect,
    generate_demand_realization,
    smooth_annual_factor,
)
from binsight.district import BinSpec


ROOT = Path(__file__).resolve().parents[1]


def _bins():
    return [
        BinSpec(
            "TEST-RES",
            1,
            3.06,
            101.57,
            30,
            0,
            540.0,
            "residential",
            site_id="SITE-RES",
        ),
        BinSpec(
            "TEST-COM",
            2,
            3.07,
            101.58,
            5,
            4,
            540.0,
            "mixed/commercial",
            site_id="SITE-COM",
        ),
    ]


def test_recurring_factors_keep_long_run_mean_and_intended_patterns():
    config = load_config(ROOT / "config.json")
    hours = np.arange(365 * 24)
    residential = deterministic_seasonal_factor(
        _bins()[0], config, hours, commercial=False
    )
    commercial = deterministic_seasonal_factor(
        _bins()[1], config, hours, commercial=True
    )

    np.testing.assert_allclose(residential.mean(), 1.0, atol=1e-3)
    np.testing.assert_allclose(commercial.mean(), 1.0, atol=1e-3)
    # Residential evenings and commercial working hours retain distinct peaks.
    assert residential.reshape(365, 24)[:, 19].mean() > residential.reshape(365, 24)[:, 3].mean()
    assert commercial.reshape(365, 24)[:, 10].mean() > commercial.reshape(365, 24)[:, 2].mean()
    # The full product varies across weekdays and seasons instead of a weekend binary.
    assert np.ptp([residential[day * 24 : (day + 1) * 24].mean() for day in range(7)]) > 0.05
    assert np.ptp([commercial[day * 24 : (day + 30) * 24].mean() for day in range(0, 330, 30)]) > 0.05


def test_monthly_and_annual_cycles_are_continuous_across_new_year():
    pattern = np.linspace(0.8, 1.2, 12)
    just_before = cyclic_month_factor(
        datetime(2025, 12, 31, 23, tzinfo=timezone.utc), pattern
    )
    just_after = cyclic_month_factor(
        datetime(2026, 1, 1, 0, tzinfo=timezone.utc), pattern
    )
    assert abs(just_before - just_after) < 0.002
    assert abs(
        smooth_annual_factor(365.0, 0.2, 180.0)
        - smooth_annual_factor(0.0, 0.2, 180.0)
    ) < 0.002


def test_demand_is_nonnegative_reproducible_and_seed_sensitive_but_comparable():
    config = load_config(ROOT / "config.json")
    first = generate_demand_realization(_bins(), config, 121, 30 * 24)
    repeated = generate_demand_realization(_bins(), config, 121, 30 * 24)
    different = generate_demand_realization(_bins(), config, 122, 30 * 24)

    assert np.all(first.arrivals_kg >= 0)
    np.testing.assert_allclose(first.arrivals_kg, repeated.arrivals_kg)
    assert not np.allclose(first.arrivals_kg, different.arrivals_kg)
    relative_total_difference = abs(
        first.arrivals_kg.sum() - different.arrivals_kg.sum()
    ) / first.arrivals_kg.sum()
    assert relative_total_difference < 0.25


def test_ar1_regimes_persist_and_local_surge_is_localized():
    config = load_config(ROOT / "config.json")
    scenario = DemandScenario(
        name="localized",
        local_surge_windows=((3, 8, 1.8),),
        local_surge_bin_ids=("TEST-RES",),
    )
    result = generate_demand_realization(_bins(), config, 44, 12 * 24, scenario=scenario)
    autocorrelation = np.corrcoef(
        result.context.shared_regime[:-1], result.context.shared_regime[1:]
    )[0, 1]
    assert autocorrelation > 0.70
    surge = slice(3 * 24, 8 * 24)
    assert result.context.local_regime[surge, 0].mean() > (
        result.context.local_regime[surge, 1].mean() * 1.35
    )


def test_events_are_targeted_and_have_buildup_peak_decay_and_known_time():
    config = load_config(ROOT / "config.json")
    result = generate_demand_realization(_bins(), config, 55, 14 * 24)
    market_start = 5 * 24 + 16
    assert result.context.current_event_intensity[market_start, 1] > 0
    assert result.context.current_event_intensity[market_start, 0] == 0
    assert result.context.known_event_intensity_48h[market_start - 24, 1] > 0

    event = DemandEvent(
        event_id="shape-test",
        event_type="test",
        location="SITE-COM",
        start_hour=100,
        end_hour=106,
        buildup_hours=4,
        decay_hours=6,
        intensity=1.0,
        known_at_hour=80,
    )
    assert 0 < event_effect(event, 97) < event_effect(event, 102)
    assert 0 < event_effect(event, 107) < event_effect(event, 102)
    assert event_effect(event, 112) == 0


def test_unannounced_event_is_hidden_until_its_known_at_hour():
    config = load_config(ROOT / "config.json")
    result = generate_demand_realization(
        _bins(),
        config,
        56,
        20 * 24,
        scenario=DemandScenario(name="unannounced", add_unannounced_event=True),
    )
    event = next(
        item for item in result.context.events
        if item.event_type == "unannounced-commercial-surge"
    )
    target = 0
    assert result.context.actual_event_intensity[event.known_at_hour - 1, target] > 0
    assert result.context.current_event_intensity[event.known_at_hour - 1, target] == 0
    assert result.context.known_event_intensity_48h[event.known_at_hour - 1, target] == 0
    assert result.context.current_event_intensity[event.known_at_hour, target] > 0
    assert result.context.known_event_intensity_48h[event.known_at_hour, target] > 0


def test_trend_and_change_point_are_bounded_external_demand_changes():
    config = load_config(ROOT / "config.json")
    quiet_demand = replace(
        config.demand,
        shared_regime_sigma=0.0,
        local_regime_sigma=0.0,
        event_templates=(),
        base_trend_per_year=0.0,
    )
    deterministic = replace(config, demand=quiet_demand)
    base = generate_demand_realization(_bins(), deterministic, 9, 30 * 24)
    changed = generate_demand_realization(
        _bins(),
        deterministic,
        9,
        30 * 24,
        scenario=DemandScenario(
            name="change",
            change_point_day=12,
            change_point_multiplier=1.5,
            change_point_bin_ids=("TEST-COM",),
        ),
    )
    np.testing.assert_allclose(changed.expected_mean_kg[: 12 * 24], base.expected_mean_kg[: 12 * 24])
    np.testing.assert_allclose(
        changed.expected_mean_kg[12 * 24 :, 1],
        base.expected_mean_kg[12 * 24 :, 1] * 1.5,
    )
    np.testing.assert_allclose(
        changed.expected_mean_kg[12 * 24 :, 0], base.expected_mean_kg[12 * 24 :, 0]
    )
