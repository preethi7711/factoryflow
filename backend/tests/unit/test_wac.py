"""WAC and costing, checked against the benchmark (spec B13 and A5). Quantities in base units."""

from decimal import Decimal

import pytest

from app.core.wac import (
    Balance,
    InsufficientStockError,
    cost_per_unit_paise,
    issue_value,
    receipt_value,
)

D = Decimal


def test_receipt_value_uses_the_quoted_unit() -> None:
    assert receipt_value(D(60), 4500) == 270000  # 60 kg flour at Rs 45/kg
    assert receipt_value(D("0.333"), 4500) == 1499  # 1498.5 -> 1499, half-up


def test_flour_wac_across_two_purchases() -> None:
    # Opening 100 kg at 42 + purchase 60 kg at 45 = Rs 6,900 for 160 kg = Rs 43.125/kg.
    flour = Balance().receive(D(100000), receipt_value(D(100), 4200))
    flour = flour.receive(D(60000), receipt_value(D(60), 4500))
    value, flour = flour.issue(D(40000))
    assert value == 172500  # 40 kg x 43.125 = Rs 1,725.00
    assert flour == Balance(D(120000), 517500)  # B1: 120 kg left, still at 43.125/kg


def test_b13_cost_per_packet() -> None:
    issues = [
        issue_value(D(40000), D(160000), 690000),  # flour, WAC 43.125/kg
        issue_value(D(10500), D(30000), 420000),  # oil 10.5 L of 30 L at 140
        issue_value(D(1200), D(5000), 100000),  # spice 1.2 kg of 5 kg at 200
        issue_value(D(194), D(500), 125000),  # pouches incl. 6 damaged, at 2.50
        issue_value(D(9), D(30), 45000),  # cartons at 15
    ]
    assert issues == [172500, 147000, 24000, 48500, 13500]
    materials = sum(issues)
    assert materials == 405500  # Rs 4,055.00
    total = materials + 120000 + 60000  # + labour + gas/power
    assert total == 585500
    assert cost_per_unit_paise(total, D(188)) == 3114  # Rs 31.1436 -> Rs 31.14


def test_a5_opening_finished_goods_cost() -> None:
    standard = sum(
        receipt_value(q, r)
        for q, r in [(D(40), 4200), (D(10), 14000), (D("1.2"), 20000), (D(200), 250), (D(10), 1500)]
    )
    assert standard == 397000
    assert cost_per_unit_paise(standard, D(200)) == 1985  # Rs 19.85/pkt


def test_anti_drift_last_issue_takes_remaining_value() -> None:
    bal = Balance(D(3), 100)  # 33.33 paise each
    taken = []
    for _ in range(3):
        value, bal = bal.issue(D(1))
        taken.append(value)
    assert taken == [33, 34, 33]  # 33.33 -> 33, then 67/2 = 33.5 -> 34, then all of 33
    assert sum(taken) == 100
    assert bal == Balance(D(0), 0)  # no value left stranded on zero stock


def test_cannot_issue_more_than_on_hand() -> None:
    with pytest.raises(InsufficientStockError) as exc:
        issue_value(D(120), D(88), 174680)
    assert (exc.value.requested, exc.value.available) == (D(120), D(88))
    with pytest.raises(ValueError):
        issue_value(D(0), D(88), 174680)


def test_cost_per_unit_needs_output() -> None:
    with pytest.raises(ValueError):
        cost_per_unit_paise(585500, D(0))
