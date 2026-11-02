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
                      "unit_price": pytest.approx(14.85)}


@pytest.mark.parametrize("upstream,peers,ratio", [([], 1, 0.8), (
    [{"key": "a", "quantity_available": 100.0, "unit_price": 10.0}], 0, 0.8)])
def test_empty_zero_peers_and_zero_conversion(upstream, peers, ratio):
    agent = ProcessProviderAgent()
    agent.setup({"role": "processor", "conversion_ratio": ratio})
    assert agent.step({"upstream": upstream, "peer_count": peers})["unit_price"] == 0.0
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
                      "unit_price": pytest.approx(price)}
    assert sources[0]["quantity_available"] == available
    empty = agent.step({"peer_count": 1})
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
