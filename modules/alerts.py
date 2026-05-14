"""Alert engine for warehouse KPIs with severity scoring (1-10) and acknowledge support."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Literal

import pandas as pd

from . import kpi_calculator as kpi

Severity = Literal["red", "orange"]


@dataclass(frozen=True)
class Alert:
    severity: Severity
    title: str
    message: str
    metric: str
    severity_score: int = 1  # 1..10, higher = worse

    @property
    def alert_id(self) -> str:
        raw = f"{self.metric}|{self.title}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]


# --------------------- helpers ----------------------------------------------

def _score_picks(picks_per_hour: float) -> int:
    """Lower picks/h => higher score."""
    if picks_per_hour < 20:
        return 10
    if picks_per_hour < 25:
        return 9
    if picks_per_hour < 30:
        return 8
    if picks_per_hour < 35:
        return 6
    if picks_per_hour < 40:
        return 4
    return 2


def _score_error(rate: float) -> int:
    if rate > 6:
        return 10
    if rate > 5:
        return 9
    if rate > 4:
        return 8
    if rate > 3:
        return 7
    if rate >= 2.5:
        return 5
    if rate >= 2:
        return 3
    return 1


def _score_accuracy(acc: float) -> int:
    if acc < 94:
        return 10
    if acc < 95:
        return 9
    if acc < 96:
        return 7
    if acc < 96.5:
        return 5
    if acc < 97:
        return 3
    return 1


def _score_delay(rate: float) -> int:
    if rate > 25:
        return 10
    if rate > 20:
        return 9
    if rate > 15:
        return 7
    if rate > 10:
        return 5
    return 2


def _score_pallet_gap(gap_pct: float) -> int:
    if gap_pct > 50:
        return 10
    if gap_pct > 40:
        return 9
    if gap_pct > 30:
        return 7
    if gap_pct > 20:
        return 5
    return 2


# --------------------- checks ----------------------------------------------

def _check_picks(df: pd.DataFrame) -> list[Alert]:
    alerts: list[Alert] = []
    per_op = kpi.picks_per_hour_by_operator(df)
    for _, row in per_op.iterrows():
        value = row["picks_per_hour"]
        if value < 30:
            alerts.append(Alert(
                severity="red",
                title=f"{row['operator_name']} — critical picks/h",
                message=(
                    f"{row['operator_name']} ({row['operator_id']}): "
                    f"{value:.1f} picks/h (threshold 30)."
                ),
                metric=f"picks_per_hour:{row['operator_id']}",
                severity_score=_score_picks(value),
            ))
        elif value < 40:
            alerts.append(Alert(
                severity="orange",
                title=f"{row['operator_name']} — low picks/h",
                message=(
                    f"{row['operator_name']} ({row['operator_id']}): "
                    f"{value:.1f} picks/h (target ≥ 40)."
                ),
                metric=f"picks_per_hour:{row['operator_id']}",
                severity_score=_score_picks(value),
            ))
    return alerts


def _check_errors(df: pd.DataFrame) -> list[Alert]:
    alerts: list[Alert] = []
    per_op = kpi.error_rate_by_operator(df)
    for _, row in per_op.iterrows():
        rate = row["error_rate"]
        if rate > 3:
            alerts.append(Alert(
                severity="red",
                title=f"{row['operator_name']} — high error rate",
                message=(
                    f"{row['operator_name']} ({row['operator_id']}): "
                    f"{rate:.2f}% errors (threshold 3%)."
                ),
                metric=f"error_rate:{row['operator_id']}",
                severity_score=_score_error(rate),
            ))
        elif rate >= 2:
            alerts.append(Alert(
                severity="orange",
                title=f"{row['operator_name']} — error rate to watch",
                message=(
                    f"{row['operator_name']} ({row['operator_id']}): "
                    f"{rate:.2f}% errors."
                ),
                metric=f"error_rate:{row['operator_id']}",
                severity_score=_score_error(rate),
            ))

    per_zone = kpi.error_rate_by_zone(df)
    for _, row in per_zone.iterrows():
        rate = row["error_rate"]
        if rate > 3:
            alerts.append(Alert(
                severity="red",
                title=f"Zone {row['zone']} — error rate above threshold",
                message=f"Zone {row['zone']}: {rate:.2f}% errors (threshold 3%).",
                metric=f"error_rate_zone:{row['zone']}",
                severity_score=_score_error(rate),
            ))
        elif rate >= 2:
            alerts.append(Alert(
                severity="orange",
                title=f"Zone {row['zone']} — error rate to watch",
                message=f"Zone {row['zone']}: {rate:.2f}% errors.",
                metric=f"error_rate_zone:{row['zone']}",
                severity_score=_score_error(rate),
            ))
    return alerts


def _check_stock_accuracy(df: pd.DataFrame) -> list[Alert]:
    accuracy = kpi.stock_accuracy_mean(df)
    if accuracy == 0:
        return []
    if accuracy < 96:
        return [Alert(
            severity="red",
            title="Stock accuracy critical",
            message=f"Average stock accuracy: {accuracy:.2f}% (threshold 96%).",
            metric="stock_accuracy",
            severity_score=_score_accuracy(accuracy),
        )]
    if accuracy < 97:
        return [Alert(
            severity="orange",
            title="Stock accuracy to watch",
            message=f"Average stock accuracy: {accuracy:.2f}% (target ≥ 97%).",
            metric="stock_accuracy",
            severity_score=_score_accuracy(accuracy),
        )]
    return []


def _check_delay_rate(df: pd.DataFrame) -> list[Alert]:
    rate = kpi.order_delay_rate(df)
    if rate > 10:
        return [Alert(
            severity="red",
            title="Order delay rate high",
            message=f"Delayed orders: {rate:.1f}% (threshold 10%).",
            metric="delay_rate",
            severity_score=_score_delay(rate),
        )]
    return []


def _check_pallet_balance(df: pd.DataFrame) -> list[Alert]:
    received, dispatched = kpi.pallets_totals(df)
    if received == 0 and dispatched == 0:
        return []
    base = max(received, dispatched, 1)
    gap = abs(received - dispatched) / base * 100
    if gap > 20:
        return [Alert(
            severity="red",
            title="Reception / dispatch imbalance",
            message=(
                f"Pallet gap reception ({received}) vs dispatch ({dispatched}): "
                f"{gap:.1f}% (threshold 20%)."
            ),
            metric="pallet_balance",
            severity_score=_score_pallet_gap(gap),
        )]
    return []


def evaluate(df: pd.DataFrame, acknowledged: set[str] | None = None) -> tuple[list[Alert], list[Alert]]:
    """Return (active_alerts, acknowledged_alerts), each sorted by severity score desc."""
    alerts: list[Alert] = []
    alerts.extend(_check_picks(df))
    alerts.extend(_check_errors(df))
    alerts.extend(_check_stock_accuracy(df))
    alerts.extend(_check_delay_rate(df))
    alerts.extend(_check_pallet_balance(df))

    acknowledged = acknowledged or set()
    active = [a for a in alerts if a.alert_id not in acknowledged]
    ack = [a for a in alerts if a.alert_id in acknowledged]

    active.sort(key=lambda a: (-a.severity_score, a.title))
    ack.sort(key=lambda a: (-a.severity_score, a.title))
    return active, ack
