import copy

import jsonschema
import pytest

from provider_agents.offis_agents.transport_provider_agent import TransportProviderAgent


def source(key, quantity=100.0, price=10.0, **extra):
    return {"key": key, "quantity_available": quantity, "unit_price": price, **extra}


def transport(role="sea_transport", **params):
    agent = TransportProviderAgent()
    agent.setup({"role": role, "capacity": 100.0, "fixed_costs": 20.0,
                 "margin_transport": 0.1, **params})
    return agent


def test_movement_capacity_energy_peer_sharing_and_initial_fee():
    agent = transport()
    assert agent.unit_price == 0.22000000000000003
    result = agent.step({"upstream": [source("a")], "peer_count": 2,
                         "effects": {"capacity": 0.4, "energy": 2.0}})
    assert result == {"quantity_available": 40.0, "utilisation": 1.0,
                      "unit_price": 11.1, "received": [{"key": "a", "quantity": 40.0}]}
    assert agent.step({}) == {"quantity_available": 0.0, "utilisation": 0.0, "unit_price": 0.0,
                              "received": []}
    assert agent.step({"state": {"active": False}}) == {}


def export_input(weights=None):
    return {
        "list_name": "port_a", "peer_count": 1, "upstream": [source("a")],
        "adjacency": {"port_a": ["origin"], "port_b": ["origin"], "sea": ["port_a"]},
        "routes": [
            {"name": "port_a", "role": "land_transport", "is_transport": True, "entity_ids": ["a"]},
            {"name": "port_b", "role": "land_transport", "is_transport": True, "entity_ids": ["b"]},
            {"name": "sea", "role": "sea_transport", "is_transport": True, "entity_ids": []},
        ],
        "route_weights": weights or {},
    }


@pytest.mark.parametrize("weights,quantity", [({}, 50.0), ({"a": 0.7}, 70.0),
                                            ({"a": 2.0, "b": 2.0}, 50.0)])
def test_export_weights(weights, quantity):
    result = transport("land_transport").step(export_input(weights))
    assert result["quantity_available"] == quantity
    assert result["received"] == [{"key": "a", "quantity": quantity}]


@pytest.mark.parametrize("weights", [{"a": -1.0}, {"a": float("nan")},
                                    {"a": float("inf")}, {"a": 0.0, "b": 0.0}])
def test_bad_route_weights(weights):
    with pytest.raises(ValueError):
        transport("land_transport").step(export_input(weights))


def test_single_route_and_missing_port_entity():
    data = export_input()
    data["routes"].pop(1)
    assert transport("land_transport").step(data)["quantity_available"] == 100.0
    data["routes"][0]["entity_ids"] = []
    with pytest.raises(ValueError, match="no declared port entity"):
        transport("land_transport").step(data)


def test_cheapest_first_patches_sources_without_mutating_input():
    upstream = [source("cheap", 60.0, 1.0, is_transport=True, capacity=100.0,
                       effects={"capacity": 0.5}), source("costly", 70.0, 2.0)]
    data = {"upstream": upstream, "list_name": "import", "adjacency": {"import": ["x", "y"]}}
    original = copy.deepcopy(data)
    result = transport("land_transport", fixed_costs=0.0).step(data)
    assert result == {
        "quantity_available": 100.0, "utilisation": 1.0, "unit_price": 1.4,
        "upstream_updates": [
            {"key": "cheap", "quantity_available": 60.0, "utilisation": 1.2},
            {"key": "costly", "quantity_available": 40.0},
        ],
        "received": [{"key": "cheap", "quantity": 60.0},
                     {"key": "costly", "quantity": 40.0}],
    }
    assert data == original


@pytest.mark.parametrize("effect,quantity,utilisation", [(2.0, 100.0, 0.5), (0.5, 50.0, 1.0)])
def test_demand_target_and_tied_price_order(effect, quantity, utilisation):
    result = transport("land_transport", fixed_costs=0.0).step({
        "list_name": "import", "adjacency": {"import": ["x", "y"]},
        "effects": {"capacity": effect},
        "upstream": [source("first", 100.0), source("second", 100.0)],
    })
    assert result["quantity_available"] == quantity
    assert result["utilisation"] == utilisation
    assert result["upstream_updates"] == [
        {"key": "first", "quantity_available": quantity},
        {"key": "second", "quantity_available": 0.0},
    ]
    assert result["received"] == [{"key": "first", "quantity": quantity},
                                  {"key": "second", "quantity": 0.0}]


def test_unknown_role():
    agent = TransportProviderAgent()
    agent.setup({})
    with pytest.raises(ValueError, match="unknown role"):
        agent.step({})


def test_unused_weights_are_not_validated_and_convertible_weights_work():
    # Sea movement never consulted route weights in the original implementation.
    assert transport().step({"route_weights": {"unused": "not-a-number"}})["unit_price"] == 0.0
    result = transport("land_transport").step(export_input({"a": "0.7"}))
    assert result["quantity_available"] == 70.0


def arrived(key, delivered, spare=0.0, price=10.0):
    return source(key, delivered, price, delivered=delivered, spare=spare)


def forwarding(role, baseline, **params):
    return transport(role, baseline_orders=dict(baseline), last_orders=dict(baseline), **params)


def test_transport_on_orders_passes_on_and_forwards_demand():
    agent = forwarding("sea_transport", {"route": 70.0})
    result = agent.step({"orders": [{"key": "rotterdam", "quantity": 70.0}],
                         "upstream": [arrived("route", 70.0)]})
    assert (result["quantity_available"], result["utilisation"]) == (70.0, 0.7)
    assert result["unit_price"] == pytest.approx(10.0 + 20.0 / 70.0 * 1.1)
    assert result["deliveries"] == [{"key": "rotterdam", "quantity": 70.0}]
    assert result["orders"] == [{"key": "route", "quantity": 70.0}]
    assert "received" not in result and "upstream_updates" not in result


def test_import_port_splits_demand_by_baseline_share():
    agent = forwarding("land_transport", {"santos": 70.0, "argentina": 100.0, "us": 100.0},
                       capacity=300.0)
    result = agent.step({"orders": [{"key": "mill", "quantity": 250.0}], "upstream": [
        arrived("santos", 70.0), arrived("argentina", 100.0), arrived("us", 100.0)]})
    assert result["deliveries"] == [{"key": "mill", "quantity": 270.0}]
    share = 250.0 / 270.0
    assert {order["key"]: order["quantity"] for order in result["orders"]} == pytest.approx(
        {"santos": 70.0 * share, "argentina": 100.0 * share, "us": 100.0 * share})


def test_import_port_shifts_a_short_route():
    agent = forwarding("land_transport", {"santos": 70.0, "argentina": 100.0, "us": 100.0},
                       capacity=400.0)
    result = agent.step({"orders": [{"key": "mill", "quantity": 270.0}], "upstream": [
        arrived("santos", 40.0), arrived("argentina", 100.0, spare=20.0),
        arrived("us", 100.0, spare=5.0)]})
    assert result["deliveries"] == [{"key": "mill", "quantity": 240.0}]
    assert {order["key"]: order["quantity"] for order in result["orders"]} == pytest.approx(
        {"santos": 70.0, "argentina": 120.0, "us": 105.0})


def test_transport_passes_on_more_than_was_ordered():
    agent = forwarding("sea_transport", {"route": 80.0})
    result = agent.step({"orders": [{"key": "a", "quantity": 30.0},
                                    {"key": "b", "quantity": 10.0}],
                         "upstream": [arrived("route", 80.0)]})
    assert result["deliveries"] == [{"key": "a", "quantity": 60.0},
                                    {"key": "b", "quantity": 20.0}]
    assert result["orders"] == [{"key": "route", "quantity": 40.0}]


def test_transport_passes_on_overflow_above_capacity():
    agent = forwarding("sea_transport", {"route": 100.0})
    result = agent.step({"orders": [{"key": "a", "quantity": 100.0}],
                         "upstream": [arrived("route", 110.0)]})
    assert result["utilisation"] == pytest.approx(1.1)
    assert result["deliveries"] == [{"key": "a", "quantity": 110.0}]


def test_transport_spreads_arrivals_equally_when_nothing_was_ordered():
    agent = forwarding("sea_transport", {"route": 80.0})
    result = agent.step({"orders": [{"key": "a", "quantity": 0.0},
                                    {"key": "b", "quantity": 0.0}],
                         "upstream": [arrived("route", 50.0)]})
    assert result["deliveries"] == [{"key": "a", "quantity": 25.0},
                                    {"key": "b", "quantity": 25.0}]
    assert result["orders"] == [{"key": "route", "quantity": 0.0}]


FEE_70 = 20.0 / 70.0 * 1.1


def pipeline(steps, role="sea_transport", **params):
    return forwarding(role, {"route": 70.0}, transit_steps=steps, **params)


def ship(agent, delivered, price=10.0, ordered=70.0, **data):
    return agent.step({"orders": [{"key": "rotterdam", "quantity": ordered}],
                       "upstream": [arrived("route", delivered, price=price)], **data})


def test_zero_transit_steps_keeps_todays_forward():
    plain = forwarding("sea_transport", {"route": 70.0})
    zero = pipeline(0, in_transit=[])
    for delivered in (70.0, 40.0, 90.0, 70.0):
        expected = ship(plain, delivered)
        assert ship(zero, delivered) == expected
        assert "in_transit" not in expected


@pytest.mark.parametrize("role", ["sea_transport", "land_transport"])
def test_delivery_arrives_transit_steps_later(role):
    agent = pipeline(3, role)
    arrivals = [ship(agent, delivered)["quantity_available"]
                for delivered in (70.0, 70.0, 40.0, 70.0, 70.0, 70.0, 70.0)]
    assert arrivals == [70.0, 70.0, 70.0, 70.0, 70.0, 40.0, 70.0]


def test_seeded_pipeline_is_a_steady_state():
    agent = pipeline(3)
    for _ in range(5):
        result = ship(agent, 70.0)
        assert (result["quantity_available"], result["utilisation"]) == (70.0, 0.7)
        assert result["unit_price"] == pytest.approx(10.0 + FEE_70)
        assert result["deliveries"] == [{"key": "rotterdam", "quantity": 70.0}]
        assert result["orders"] == [{"key": "route", "quantity": 70.0}]
        assert result["in_transit"] == [{"quantity": 70.0, "value": 700.0}] * 3


def test_arriving_cargo_keeps_its_loading_price():
    agent = pipeline(2)
    prices = [ship(agent, 70.0, price)["unit_price"] for price in (10.0, 15.0, 15.0, 15.0)]
    assert prices == pytest.approx(
        [10.0 + FEE_70, 10.0 + FEE_70, 10.0 + FEE_70, 15.0 + FEE_70])


def test_pipeline_is_seeded_at_the_offer_price_when_nothing_arrives():
    agent = pipeline(2)
    result = agent.step({"orders": [{"key": "rotterdam", "quantity": 70.0}],
                         "upstream": [source("route", 70.0, 12.0, delivered=0.0)]})
    assert (result["quantity_available"], result["utilisation"]) == (70.0, 0.0)
    assert result["unit_price"] == pytest.approx(12.0 + FEE_70)
    assert result["in_transit"] == [{"quantity": 70.0, "value": 840.0},
                                    {"quantity": 0.0, "value": 0.0}]


def test_capacity_caps_the_order_not_the_cargo_on_the_way():
    agent = pipeline(2)
    halved = {"effects": {"capacity": 0.5}}
    first = ship(agent, 70.0, **halved)
    assert first["orders"] == [{"key": "route", "quantity": 50.0}]
    assert (first["quantity_available"], first["utilisation"]) == (70.0, 1.4)
    arrivals = [ship(agent, 50.0, **halved)["quantity_available"] for _ in range(3)]
    assert arrivals == [70.0, 70.0, 50.0]


def test_pipeline_conserves_volume():
    agent = pipeline(3)
    ship(agent, 70.0)
    for delivered in (20.0, 0.0, 110.0, 55.0, 70.0):
        before = sum(slot["quantity"] for slot in agent.in_transit)
        result = ship(agent, delivered)
        after = sum(slot["quantity"] for slot in result["in_transit"])
        assert before + delivered == pytest.approx(after + result["quantity_available"])
        assert sum(entry["quantity"] for entry in result["deliveries"]) == pytest.approx(
            result["quantity_available"])


def test_transit_slots_are_validated():
    pipeline(2, in_transit=[{"quantity": 70.0, "value": 700.0}] * 2)
    for slot in ({"quantity": -1.0, "value": 0.0}, {"quantity": 70.0},
                 {"quantity": 70.0, "value": 700.0, "price": 10.0}):
        with pytest.raises(jsonschema.ValidationError):
            pipeline(2, in_transit=[slot])
