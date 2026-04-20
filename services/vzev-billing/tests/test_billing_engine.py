"""Unit tests for VZEV billing allocation logic (no DB required)."""

from uuid import UUID, uuid4

import pytest

from billing_engine import MemberState, allocate_interval, IntervalResult


# ── Proportional allocation ───────────────────────────────────────────────────

def test_proportional_two_participants_equal_consumption():
    m1_id, m2_id = uuid4(), uuid4()
    members = [
        MemberState(m1_id, uuid4(), "proportional", 0.0),
        MemberState(m2_id, uuid4(), "proportional", 0.0),
    ]
    consumptions = {m1_id: 1.0, m2_id: 1.0}

    results = allocate_interval(2.0, consumptions, members)

    by_id = {r.membership_id: r for r in results}
    assert by_id[m1_id].allocated_kwh == pytest.approx(1.0)
    assert by_id[m2_id].allocated_kwh == pytest.approx(1.0)
    assert by_id[m1_id].grid_draw_kwh == pytest.approx(0.0)
    assert by_id[m2_id].grid_draw_kwh == pytest.approx(0.0)


def test_proportional_production_insufficient():
    """When production < total consumption, each participant gets partial allocation."""
    m1_id, m2_id = uuid4(), uuid4()
    members = [
        MemberState(m1_id, uuid4(), "proportional", 0.0),
        MemberState(m2_id, uuid4(), "proportional", 0.0),
    ]
    consumptions = {m1_id: 2.0, m2_id: 2.0}

    results = allocate_interval(1.0, consumptions, members)

    by_id = {r.membership_id: r for r in results}
    # Each gets 50% of 1 kWh = 0.5 kWh
    assert by_id[m1_id].allocated_kwh == pytest.approx(0.5)
    assert by_id[m2_id].allocated_kwh == pytest.approx(0.5)
    # Each still needs 2 - 0.5 = 1.5 kWh from grid
    assert by_id[m1_id].grid_draw_kwh == pytest.approx(1.5)
    assert by_id[m2_id].grid_draw_kwh == pytest.approx(1.5)


def test_proportional_unequal_consumption():
    """Heavy consumer gets more allocation but also more grid draw if needed."""
    m1_id, m2_id = uuid4(), uuid4()
    members = [
        MemberState(m1_id, uuid4(), "proportional", 0.0),
        MemberState(m2_id, uuid4(), "proportional", 0.0),
    ]
    # m1 consumes 3x more than m2
    consumptions = {m1_id: 3.0, m2_id: 1.0}

    results = allocate_interval(2.0, consumptions, members)

    by_id = {r.membership_id: r for r in results}
    # m1 share = 3/4, m2 share = 1/4
    assert by_id[m1_id].allocated_kwh == pytest.approx(1.5)   # min(2*0.75, 3.0)
    assert by_id[m2_id].allocated_kwh == pytest.approx(0.5)   # min(2*0.25, 1.0)
    assert by_id[m1_id].grid_draw_kwh == pytest.approx(1.5)   # 3.0 - 1.5
    assert by_id[m2_id].grid_draw_kwh == pytest.approx(0.5)   # 1.0 - 0.5


def test_surplus_production_no_grid_draw():
    """When production > total demand, all consumption is covered; no grid draw."""
    m1_id = uuid4()
    members = [MemberState(m1_id, uuid4(), "proportional", 0.0)]
    consumptions = {m1_id: 1.0}

    results = allocate_interval(5.0, consumptions, members)

    r = results[0]
    assert r.allocated_kwh == pytest.approx(1.0)   # capped at actual consumption
    assert r.grid_draw_kwh == pytest.approx(0.0)


# ── Static allocation ─────────────────────────────────────────────────────────

def test_static_allocation():
    m1_id, m2_id = uuid4(), uuid4()
    members = [
        MemberState(m1_id, uuid4(), "static", 0.7),
        MemberState(m2_id, uuid4(), "static", 0.3),
    ]
    consumptions = {m1_id: 10.0, m2_id: 10.0}

    results = allocate_interval(10.0, consumptions, members)

    by_id = {r.membership_id: r for r in results}
    assert by_id[m1_id].allocated_kwh == pytest.approx(7.0)
    assert by_id[m2_id].allocated_kwh == pytest.approx(3.0)
    assert by_id[m1_id].grid_draw_kwh == pytest.approx(3.0)
    assert by_id[m2_id].grid_draw_kwh == pytest.approx(7.0)


# ── Edge cases ────────────────────────────────────────────────────────────────

def test_zero_production():
    m1_id = uuid4()
    members = [MemberState(m1_id, uuid4(), "proportional", 0.0)]
    consumptions = {m1_id: 2.0}

    results = allocate_interval(0.0, consumptions, members)

    r = results[0]
    assert r.allocated_kwh == pytest.approx(0.0)
    assert r.grid_draw_kwh == pytest.approx(2.0)


def test_empty_members():
    results = allocate_interval(5.0, {}, [])
    assert results == []


def test_zero_consumption_proportional_fallback():
    """When all proportional members report zero consumption, equal fallback applies."""
    m1_id, m2_id = uuid4(), uuid4()
    members = [
        MemberState(m1_id, uuid4(), "proportional", 0.0),
        MemberState(m2_id, uuid4(), "proportional", 0.0),
    ]
    consumptions = {m1_id: 0.0, m2_id: 0.0}

    results = allocate_interval(4.0, consumptions, members)

    by_id = {r.membership_id: r for r in results}
    # Equal fallback: each gets 2 kWh allocated, but consumption is 0 so it's capped
    assert by_id[m1_id].allocated_kwh == pytest.approx(0.0)
    assert by_id[m2_id].allocated_kwh == pytest.approx(0.0)
