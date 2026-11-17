import jsonschema
import pytest

from provider_agents.offis_agents.process_provider_agent import ProcessProviderAgent


@pytest.mark.parametrize("role", ["processor", "feed_manufacturer"])
def test_conversion_capacity_and_price(role):
    agent = ProcessProviderAgent()
    agent.setup({"role": role, "conversion_ratio": 0.8, "fixed_costs": 20.0, "margin": 0.1})
    result = agent.step({"peer_count": 2, "effects": {"capacity": 0.5}, "upstream": [
        {"key": "a", "quantity_available": 100.0, "unit_price": 10.0},
    ]})
    assert result == {"input_received": 50.0, "input_processed": 25., "unused_input": 25.,
                      "quantity_available": 20.0,
                      "unit_price": pytest.approx(14.85),
                      "stock": 50.0, "received": [{"key": "a", "quantity": 50.0}]}


@pytest.mark.parametrize("upstream,peers,ratio", [([], 1, 0.8), (
    [{"key": "a", "quantity_available": 100.0, "unit_price": 10.0}], 0, 0.8)])
def test_empty_zero_peers_and_zero_conversion(upstream, peers, ratio):
    agent = ProcessProviderAgent()
    agent.setup({"role": "processor", "conversion_ratio": ratio})
    result = agent.step({"upstream": upstream, "peer_count": peers})
    assert result["unit_price"] == 0.0
    assert result["received"] == [{"key": source["key"], "quantity": 0.0}
                                  for source in upstream]
    assert agent.step({"state": {"active": False}}) == {}


def test_unknown_role_remains_noop():
    agent = ProcessProviderAgent()
    agent.setup({})
    assert agent.step({}) == {}


@pytest.mark.parametrize("capacity,effect,available,processed,unused,output,price", [
    (50., 1., 100., 50., 50., 40., 14.3),
    (50., .5, 100., 25., 75., 20., 14.85),
    (50., .5, 20., 20., 0., 16., 15.125),
    (0., 1., 100., 0., 100., 0., 0.),
    (None, .5, 100., 50., 50., 40., 14.3),
    (None, 2., 100., 100., 0., 80., 14.025),
])
def test_throughput_is_distinct_from_yield(capacity, effect, available,
                                          processed, unused, output, price):
    agent = ProcessProviderAgent()
    agent.setup({"role": "processor", "conversion_ratio": .8,
                 "throughput_capacity": capacity, "fixed_costs": 20., "margin": .1})
    sources = [{"key": "a", "quantity_available": available, "unit_price": 10.}]
    result = agent.step({"peer_count": 1, "effects": {"capacity": effect},
                         "upstream": sources})
    assert result == {"input_received": available, "input_processed": processed,
                      "unused_input": unused, "quantity_available": output,
                      "unit_price": pytest.approx(price),
                      "stock": available, "received": [{"key": "a", "quantity": available}]}
    assert sources[0]["quantity_available"] == available
    empty = agent.step({"peer_count": 1})
    assert empty.pop("received") == []
    assert all(value == 0 for value in empty.values())


def test_unequal_input_prices_reconcile_with_processed_cost():
    agent = ProcessProviderAgent()
    agent.setup({"role": "processor", "conversion_ratio": .8,
                 "throughput_capacity": 25., "fixed_costs": 20.})
    result = agent.step({"peer_count": 2, "upstream": [
        {"key": "a", "quantity_available": 40., "unit_price": 10.},
        {"key": "b", "quantity_available": 60., "unit_price": 20.},
    ]})
    assert result["input_received"] == 50.
    assert result["input_processed"] == 25.
    assert result["quantity_available"] == 20.
    assert result["unit_price"] == 21.  # (25 * 16 + 20) / 20
    assert result["received"] == [{"key": "a", "quantity": 20.},
                                  {"key": "b", "quantity": 30.}]


def test_unprocessed_and_untaken_input_carries_over():
    agent = ProcessProviderAgent()
    agent.setup({"role": "processor", "conversion_ratio": .8, "throughput_capacity": 60.})
    supply = [{"key": "a", "quantity_available": 100., "unit_price": 10.}]
    first = agent.step({"peer_count": 1, "upstream": supply})
    assert (first["stock"], first["input_processed"], first["unused_input"]) == (100., 60., 40.)
    second = agent.step({"peer_count": 1, "upstream": supply, "shipped": 48.})
    assert (second["stock"], second["input_processed"], second["unused_input"]) == (140., 60., 80.)
    third = agent.step({"peer_count": 1, "upstream": supply, "shipped": 24.})
    assert (third["stock"], third["unused_input"]) == (210., 150.)
    idle = agent.step({"peer_count": 1, "shipped": 48.})
    assert (idle["stock"], idle["input_processed"], idle["quantity_available"]) == (150., 60., 48.)
    assert idle["unit_price"] == first["unit_price"]
    assert idle["received"] == []


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("field,value", [
    ("conversion_ratio", 0.), ("conversion_ratio", -1.),
    ("conversion_ratio", float("nan")), ("throughput_capacity", -1.),
    ("throughput_capacity", float("inf")), ("throughput_capacity", True),
])
def test_invalid_processing_state(field, value, fallback, monkeypatch):
    from provider_agents import abstract_provider_agent as contract

    if fallback:
        monkeypatch.setattr(contract, "jsonschema", None)
    agent = ProcessProviderAgent()
    agent.setup({"role": "processor"})
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        agent.step({"state": {field: value}})


@pytest.mark.parametrize("fallback", [False, True])
@pytest.mark.parametrize("field,value", [
    ("peer_count", -1), ("peer_count", 1.5), ("peer_count", True),
    ("quantity_available", -1.), ("quantity_available", float("nan")),
    ("unit_price", -1.), ("unit_price", float("inf")), ("unit_price", True),
    ("effect", float("nan")), ("effect", -1.),
])
def test_invalid_processing_observations(field, value, fallback, monkeypatch):
    import jsonschema

    from provider_agents import abstract_provider_agent as contract

    if fallback:
        monkeypatch.setattr(contract, "jsonschema", None)
    agent = ProcessProviderAgent()
    agent.setup({"role": "processor"})
    message = {"peer_count": 1, "effects": {}, "upstream": [
        {"key": "a", "quantity_available": 100., "unit_price": 10.},
    ]}
    if field == "peer_count":
        message[field] = value
    elif field == "effect":
        message["effects"]["capacity"] = value
    else:
        message["upstream"][0][field] = value
    with pytest.raises((ValueError, jsonschema.ValidationError)):
        agent.step(message)


def delivery(key, delivered, price=10.0, spare=0.0):
    return {"key": key, "quantity_available": delivered, "unit_price": price,
            "delivered": delivered, "spare": spare}


def mill(baseline, **state):
    agent = ProcessProviderAgent()
    agent.setup({"role": "processor", "conversion_ratio": 0.8,
                 "baseline_orders": dict(baseline), "last_orders": dict(baseline), **state})
    return agent


def test_mill_on_orders_processes_delivers_and_reorders():
    agent = mill({"rotterdam": 270.0, "hamburg": 30.0}, throughput_capacity=400.0,
                 fixed_costs=20.0, margin=0.1)
    result = agent.step({"orders": [{"key": "feed_mill", "quantity": 240.0}],
                         "upstream": [delivery("rotterdam", 270.0), delivery("hamburg", 30.0)]})
    assert (result["input_received"], result["input_processed"], result["unused_input"],
            result["quantity_available"]) == (300.0, 300.0, 0.0, 240.0)
    assert result["unit_price"] == pytest.approx((10.0 / 0.8 + 20.0 / 240.0) * 1.1)
    assert result["deliveries"] == [{"key": "feed_mill", "quantity": 240.0}]
    assert result["orders"] == [{"key": "rotterdam", "quantity": 270.0},
                                {"key": "hamburg", "quantity": 30.0}]
    assert "received" not in result


def test_capped_mill_stops_growing_on_orders():
    agent = mill({"rotterdam": 270.0, "hamburg": 30.0}, throughput_capacity=250.0)
    buyer = [{"key": "feed_mill", "quantity": 200.0}]
    first = agent.step({"orders": buyer, "upstream": [delivery("rotterdam", 270.0),
                                                       delivery("hamburg", 30.0)]})
    assert (first["input_processed"], first["unused_input"]) == (250.0, 50.0)
    assert {order["key"]: order["quantity"] for order in first["orders"]} == pytest.approx(
        {"rotterdam": 180.0, "hamburg": 20.0})
    second = agent.step({"orders": buyer, "shipped": 200.0, "upstream": [
        delivery("rotterdam", 180.0), delivery("hamburg", 20.0)]})
    assert (second["stock"], second["unused_input"]) == (250.0, 0.0)
    assert sum(order["quantity"] for order in second["orders"]) == pytest.approx(250.0)
    third = agent.step({"orders": buyer, "shipped": 200.0, "upstream": [
        delivery("rotterdam", 225.0), delivery("hamburg", 25.0)]})
    assert (third["stock"], third["unused_input"]) == (250.0, 0.0)


def test_mill_shifts_a_short_port_to_the_other():
    agent = mill({"rotterdam": 270.0, "hamburg": 30.0})
    result = agent.step({"orders": [], "upstream": [
        delivery("rotterdam", 200.0), delivery("hamburg", 30.0, spare=50.0)]})
    assert result["input_received"] == 230.0
    assert result["orders"] == [{"key": "rotterdam", "quantity": 270.0},
                                {"key": "hamburg", "quantity": 80.0}]


def test_mill_ships_short_output_proportionally():
    agent = mill({"rotterdam": 150.0})
    result = agent.step({"orders": [{"key": "a", "quantity": 160.0},
                                    {"key": "b", "quantity": 80.0}],
                         "upstream": [delivery("rotterdam", 150.0)]})
    assert result["quantity_available"] == 120.0
    assert result["deliveries"] == [{"key": "a", "quantity": 80.0},
                                    {"key": "b", "quantity": 40.0}]


def test_unsold_output_counts_against_the_order_limit():
    agent = mill({"rotterdam": 300.0}, throughput_capacity=400.0)
    first = agent.step({"orders": [{"key": "feed_mill", "quantity": 100.0}],
                        "upstream": [delivery("rotterdam", 300.0)]})
    assert first["deliveries"] == [{"key": "feed_mill", "quantity": 100.0}]
    assert first["orders"] == [{"key": "rotterdam", "quantity": 225.0}]
    second = agent.step({"orders": [], "shipped": 100.0,
                         "upstream": [delivery("rotterdam", 225.0)]})
    assert second["stock"] == 400.0
