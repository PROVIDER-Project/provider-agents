import pytest

from provider_agents.offis_agents._common import allocate, place_orders


def quantities(entries):
    return {entry["key"]: entry["quantity"] for entry in entries}


def source(key, delivered, spare):
    return {"key": key, "quantity_available": 0.0, "unit_price": 0.0,
            "delivered": delivered, "spare": spare}


def test_allocate_fills_every_order_when_stock_suffices():
    orders = [{"key": "a", "quantity": 70.0}, {"key": "b", "quantity": 30.0}]
    assert quantities(allocate(orders, 120.0)) == {"a": 70.0, "b": 30.0}


def test_allocate_scales_every_order_by_the_same_factor_when_short():
    orders = [{"key": "a", "quantity": 70.0}, {"key": "b", "quantity": 30.0}]
    assert quantities(allocate(orders, 40.0)) == pytest.approx({"a": 28.0, "b": 12.0})


def test_allocate_ships_nothing_without_orders_or_stock():
    assert allocate([], 50.0) == []
    orders = [{"key": "a", "quantity": 10.0}]
    assert quantities(allocate(orders, -5.0)) == {"a": 0.0}
    assert quantities(allocate([{"key": "a", "quantity": 0.0}], 50.0)) == {"a": 0.0}


def test_orders_stay_at_baseline_without_a_shortfall():
    baseline = {"0": 70.0, "1": 100.0, "2": 100.0}
    upstream = [source("0", 70.0, 0.0), source("1", 100.0, 0.0), source("2", 100.0, 0.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline))) == baseline


def test_shortfall_moves_to_the_other_supplier_next_tick():
    baseline = {"p1": 70.0, "p2": 30.0}
    upstream = [source("p1", 40.0, 0.0), source("p2", 30.0, 30.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline))) == {
        "p1": 70.0, "p2": 60.0,
    }


def test_shortfall_is_shifted_in_two_rounds_and_the_rest_dropped():
    baseline = {"0": 70.0, "1": 100.0, "2": 100.0}
    upstream = [source("0", 40.0, 0.0), source("1", 100.0, 20.0), source("2", 100.0, 5.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline))) == pytest.approx(
        {"0": 70.0, "1": 120.0, "2": 105.0})


def test_shortfall_is_dropped_when_nobody_has_spare():
    baseline = {"0": 70.0, "1": 100.0}
    upstream = [source("0", 40.0, 0.0), source("1", 100.0, 0.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline))) == baseline


def test_supplier_without_baseline_receives_shifted_orders():
    baseline = {"0": 100.0, "1": 0.0}
    upstream = [source("0", 60.0, 0.0), source("1", 0.0, 50.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline))) == {
        "0": 100.0, "1": 40.0,
    }


def test_limit_caps_the_baseline_before_the_shortfall_is_shifted():
    baseline = {"0": 70.0, "1": 100.0, "2": 100.0}
    upstream = [source("0", 40.0, 0.0), source("1", 100.0, 20.0), source("2", 100.0, 5.0)]
    orders = quantities(place_orders(upstream, baseline, dict(baseline), limit=250.0))
    scale = 250.0 / 270.0
    assert orders == pytest.approx({"0": 70.0 * scale, "1": 100.0 * scale + 20.0,
                                    "2": 100.0 * scale + 5.0})


def test_shift_is_not_cut_by_the_limit():
    baseline = {"a": 40.0, "b": 40.0}
    upstream = [source("a", 20.0, 0.0), source("b", 40.0, 30.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline), limit=80.0)) == {
        "a": 40.0, "b": 60.0,
    }


def test_nothing_is_shifted_when_the_buyer_is_over_its_limit():
    baseline = {"0": 70.0, "1": 100.0, "2": 100.0}
    upstream = [source("0", 40.0, 0.0), source("1", 100.0, 20.0), source("2", 100.0, 5.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline), limit=-10.0)) == {
        "0": 0.0, "1": 0.0, "2": 0.0,
    }


def test_limit_at_or_below_zero_orders_nothing():
    baseline = {"0": 70.0, "1": 30.0}
    upstream = [source("0", 70.0, 0.0), source("1", 30.0, 0.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline), limit=-10.0)) == {
        "0": 0.0, "1": 0.0,
    }
