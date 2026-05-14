"""Realistic warehouse data generator with shift, fatigue, weekday and incident effects."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)

OPERATORS = [
    ("OP001", "Lucas Martin"),
    ("OP002", "Emma Bernard"),
    ("OP003", "Hugo Dubois"),
    ("OP004", "Chloe Thomas"),
    ("OP005", "Louis Robert"),
    ("OP006", "Manon Richard"),
    ("OP007", "Nathan Petit"),
    ("OP008", "Lea Durand"),
    ("OP009", "Jules Moreau"),
    ("OP010", "Sarah Laurent"),
    ("OP011", "Adam Simon"),
    ("OP012", "Camille Michel"),
    ("OP013", "Raphael Lefebvre"),
    ("OP014", "Ines Leroy"),
    ("OP015", "Tom Roux"),
    ("OP016", "Jade Fournier"),
    ("OP017", "Liam Girard"),
    ("OP018", "Lina Bonnet"),
    ("OP019", "Noah Lambert"),
    ("OP020", "Mila Faure"),
]

ZONES = ["A", "B", "C", "D", "E"]
SHIFTS = ["Morning", "Afternoon", "Night"]
ORDER_STATUSES = ["Completed", "Delayed", "Cancelled"]
DOCKS = [f"DOCK-{i}" for i in range(1, 9)]

# Picks/h ranges per shift (mean, std)
SHIFT_PROFILES = {
    "Morning":   {"low": 55, "high": 75, "start_hour": 6,  "length": 8},
    "Afternoon": {"low": 45, "high": 60, "start_hour": 14, "length": 8},
    "Night":     {"low": 30, "high": 45, "start_hour": 22, "length": 8},
}

# Weekday productivity multiplier (Mon=0 ... Sun=6)
WEEKDAY_MULTIPLIER = {
    0: 1.10,  # Monday
    1: 1.00,  # Tuesday
    2: 1.00,  # Wednesday
    3: 1.00,  # Thursday
    4: 1.10,  # Friday
    5: 0.95,  # Saturday
    6: 0.92,  # Sunday
}

FATIGUE_PER_HOUR = 0.5  # picks/h drop per hour into shift


def shift_for_hour(hour: int) -> str:
    if 6 <= hour < 14:
        return "Morning"
    if 14 <= hour < 22:
        return "Afternoon"
    return "Night"


def hours_into_shift(hour: int) -> int:
    """How many hours into the current shift the given hour is (0-based)."""
    shift = shift_for_hour(hour)
    start = SHIFT_PROFILES[shift]["start_hour"]
    diff = (hour - start) % 24
    return diff


def _operator_skill(idx: int) -> float:
    """Deterministic skill bias per operator id, ~[-1, 1]."""
    return ((idx * 7) % 11 - 5) / 5.0


def _row_for(timestamp: pd.Timestamp, idx: int, *, incident_picks: int | None = None) -> dict:
    op_id, op_name = OPERATORS[idx]
    zone = ZONES[idx % len(ZONES)]
    dock = DOCKS[idx % len(DOCKS)]

    shift = shift_for_hour(timestamp.hour)
    profile = SHIFT_PROFILES[shift]
    base_low = profile["low"]
    base_high = profile["high"]
    base_mid = (base_low + base_high) / 2

    skill = _operator_skill(idx)
    weekday_mult = WEEKDAY_MULTIPLIER[timestamp.dayofweek]
    fatigue = FATIGUE_PER_HOUR * hours_into_shift(timestamp.hour)

    target = base_mid + skill * 6.0 - fatigue
    target *= weekday_mult
    picks = int(np.clip(RNG.normal(target, 5.0), base_low - 5, base_high + 8))
    picks = max(picks, 5)

    if incident_picks is not None:
        picks = incident_picks  # forced low value due to incident

    # Inverse correlation: faster pickers make slightly more errors
    base_error_rate = 0.012
    speed_factor = (picks - base_mid) / max(base_mid, 1)
    error_rate = float(np.clip(base_error_rate + speed_factor * 0.010 - skill * 0.004, 0.002, 0.06))
    errors = int(RNG.binomial(picks, error_rate))
    errors = min(errors, 5)

    distance = float(np.round(picks * RNG.uniform(8.5, 14.5), 1))
    items_scanned = int(picks * RNG.integers(1, 4))

    # Faster pickers tend to be more accurate on stock counting (still random)
    stock_accuracy = float(np.round(
        np.clip(RNG.normal(98.0 + skill * 0.4, 0.8), 94.0, 99.9), 2,
    ))

    orders_processed = int(max(1, RNG.poisson(max(1, picks / 12))))
    if shift == "Night":
        status_weights = [0.82, 0.13, 0.05]
    else:
        status_weights = [0.90, 0.07, 0.03]
    order_status = RNG.choice(ORDER_STATUSES, p=status_weights)

    reception_pallets = int(RNG.integers(0, 12))
    dispatch_pallets = int(RNG.integers(0, 12))

    return {
        "timestamp": timestamp,
        "operator_id": op_id,
        "operator_name": op_name,
        "zone": zone,
        "shift": shift,
        "picks_completed": picks,
        "picks_errors": errors,
        "distance_m": distance,
        "items_scanned": items_scanned,
        "stock_accuracy": stock_accuracy,
        "orders_processed": orders_processed,
        "order_status": order_status,
        "dock_id": dock,
        "reception_pallets": reception_pallets,
        "dispatch_pallets": dispatch_pallets,
    }


def _generate_incidents(timestamps: pd.DatetimeIndex) -> dict[tuple[pd.Timestamp, int], int]:
    """Return a mapping (hour-truncated timestamp, operator_idx) -> forced low picks."""
    incidents: dict[tuple[pd.Timestamp, int], int] = {}
    unique_days = pd.Series(timestamps.date).unique()
    for day in unique_days:
        n_incidents = int(RNG.integers(2, 4))  # 2-3 per day
        for _ in range(n_incidents):
            op_idx = int(RNG.integers(0, len(OPERATORS)))
            start_hour = int(RNG.integers(0, 24))
            duration = int(RNG.integers(1, 3))  # 1-2 hours
            forced_picks = int(RNG.integers(20, 26))  # 20-25
            for h in range(duration):
                ts = pd.Timestamp(day) + timedelta(hours=start_hour + h)
                incidents[(ts, op_idx)] = forced_picks
    return incidents


def generate(days: int = 30, output_path: str | Path | None = None) -> pd.DataFrame:
    """Generate the synthetic warehouse dataset."""
    end = datetime.now().replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=days)
    timestamps = pd.date_range(start=start, end=end, freq="h", inclusive="left")
    incidents = _generate_incidents(timestamps)

    rows: list[dict] = []
    for ts in timestamps:
        active_count = int(RNG.integers(8, 16))
        active_ids = RNG.choice(len(OPERATORS), size=active_count, replace=False)
        for idx in active_ids:
            forced = incidents.get((ts, int(idx)))
            rows.append(_row_for(ts, int(idx), incident_picks=forced))

    df = pd.DataFrame(rows).sort_values("timestamp").reset_index(drop=True)

    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)

    return df


def append_live_tick(csv_path: str | Path) -> pd.DataFrame:
    """Append a single fresh row simulating live warehouse activity, then return the new dataframe.

    Each invocation:
      - picks a random currently-active operator
      - generates one row at the current minute
      - appends it to the CSV and returns the full dataframe
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return generate(days=30, output_path=csv_path)

    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    now = pd.Timestamp.now().floor("min")
    idx = int(RNG.integers(0, len(OPERATORS)))
    new_row = _row_for(now, idx)
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    df = df.sort_values("timestamp").reset_index(drop=True)
    df.to_csv(csv_path, index=False)
    return df


if __name__ == "__main__":
    target = Path(__file__).parent / "sample_data.csv"
    df = generate(days=30, output_path=target)
    print(f"Generated {len(df):,} rows -> {target}")
