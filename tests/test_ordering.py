import itertools
import random

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


def test_shift_is_not_cut_by_a_soft_limit():
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


def test_a_short_source_that_still_has_spare_is_late_not_out():
    orders = place_orders([source("a", 60.0, 20.0), source("b", 100.0, 50.0)],
                          {"a": 100.0, "b": 100.0}, {"a": 100.0, "b": 100.0})
    assert quantities(orders) == {"a": 100.0, "b": 100.0}


def test_the_whole_shortfall_is_shifted_by_baseline_share():
    baseline = {"a": 100.0, "b": 100.0, "c": 100.0}
    upstream = [source("a", 0.0, 0.0), source("b", 100.0, 100.0), source("c", 100.0, 100.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline))) == {
        "a": 100.0, "b": 150.0, "c": 150.0,
    }


def test_the_shift_does_not_depend_on_the_order_of_sources():
    baseline = {"a": 100.0, "b": 50.0, "c": 150.0}
    upstream = [source("a", 0.0, 0.0), source("b", 50.0, 500.0), source("c", 150.0, 500.0)]
    expected = {"a": 100.0, "b": 75.0, "c": 225.0}
    assert quantities(place_orders(upstream, baseline, dict(baseline))) == expected
    reordered = [upstream[0], upstream[2], upstream[1]]
    assert quantities(place_orders(reordered, baseline, dict(baseline))) == expected


def test_the_shift_does_not_depend_on_the_order_of_short_sources():
    baseline = {"a": 1.0, "b": 2.0, "c": 1.0, "d": 2.0, "e": 3.0}
    upstream = [source("a", 0.0, 0.0), source("b", 0.0, 0.0), source("c", 1.0, 1.0),
                source("d", 2.0, 3.0), source("e", 3.0, 1.0)]
    expected = {"a": 1.0, "b": 2.0, "c": 1.6, "d": 3.4, "e": 4.0}
    for ordering in itertools.permutations(upstream):
        orders = place_orders(list(ordering), baseline, dict(baseline))
        assert quantities(orders) == pytest.approx(expected)


def test_a_hard_limit_shift_does_not_depend_on_the_order_of_short_sources():
    baseline = {"a": 1.0, "b": 2.0, "c": 1.0, "d": 2.0, "e": 3.0}
    upstream = [source("a", 0.0, 0.0), source("b", 0.0, 0.0), source("c", 1.0, 1.0),
                source("d", 2.0, 3.0), source("e", 3.0, 1.0)]
    expected = {"a": 1.0, "b": 2.0, "c": 97 / 66, "d": 100 / 33, "e": 4.0}
    for ordering in itertools.permutations(upstream):
        orders = place_orders(list(ordering), baseline, dict(baseline), limit=11.5, hard=True)
        assert quantities(orders) == pytest.approx(expected)


def test_shifted_orders_never_depend_on_the_order_of_sources():
    rng = random.Random(5)
    for _ in range(300):
        keys = [str(index) for index in range(rng.randint(2, 6))]
        baseline = {key: float(rng.choice([0, 1, 2, 5, 10])) for key in keys}
        upstream = [source(key, rng.choice([0.0, baseline[key]]),
                           float(rng.choice([0, 0, 1, 3, 8]))) for key in keys]
        limit = rng.choice([None, sum(baseline.values()) + rng.choice([0, 2, 5])])
        hard = rng.random() < 0.5
        expected = quantities(place_orders(upstream, baseline, dict(baseline), limit, hard))
        for _ in range(5):
            shuffled = rng.sample(upstream, len(upstream))
            orders = place_orders(shuffled, baseline, dict(baseline), limit, hard)
            assert quantities(orders) == pytest.approx(expected)


def test_a_hard_limit_caps_the_shift_as_well():
    baseline = {"a": 40.0, "b": 40.0}
    upstream = [source("a", 20.0, 0.0), source("b", 40.0, 30.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline), limit=80.0,
                                   hard=True)) == {"a": 40.0, "b": 40.0}
    assert quantities(place_orders(upstream, baseline, dict(baseline), limit=90.0,
                                   hard=True)) == {"a": 40.0, "b": 50.0}


def test_a_hard_limit_splits_the_room_by_baseline_share():
    baseline = {"a": 100.0, "b": 100.0, "c": 100.0}
    upstream = [source("a", 0.0, 0.0), source("b", 100.0, 100.0), source("c", 100.0, 100.0)]
    assert quantities(place_orders(upstream, baseline, dict(baseline), limit=340.0,
                                   hard=True)) == {"a": 100.0, "b": 120.0, "c": 120.0}
