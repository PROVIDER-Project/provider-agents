import copy

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
                      "unit_price": 11.1}
    assert agent.step({}) == {"quantity_available": 0.0, "utilisation": 0.0, "unit_price": 0.0}
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
    assert transport("land_transport").step(export_input(weights))["quantity_available"] == quantity


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


def test_unknown_role():
    agent = TransportProviderAgent()
    agent.setup({})
    with pytest.raises(ValueError, match="unknown role"):
        agent.step({})
