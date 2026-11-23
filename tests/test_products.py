import pytest

from provider_agents.offis_agents.farmer_provider_agent import FarmerProviderAgent
from provider_agents.offis_agents.process_provider_agent import ProcessProviderAgent
from provider_agents.offis_agents.trader_provider_agent import TraderProviderAgent
from provider_agents.offis_agents.transport_provider_agent import TransportProviderAgent


def arrived(key, quantity, product=None):
    record = {"key": key, "quantity_available": quantity, "unit_price": 10.0,
              "delivered": quantity, "spare": 0.0}
    return {**record, "product": product} if product else record


def ordering(agent_type, role, baseline, **state):
    agent = agent_type()
    agent.setup({"role": role, "baseline_orders": dict(baseline),
                 "last_orders": dict(baseline), **state})
    return agent


def test_producer_delivers_its_product():
    agent = FarmerProviderAgent()
    agent.setup({"role": "producer", "base_yield": 100.0, "product": "soybean"})
    result = agent.step({"orders": [{"key": "w", "quantity": 100.0}]})
    assert result["deliveries"] == [{"key": "w", "quantity": 100.0, "product": "soybean"}]


def test_wholesaler_delivers_its_product_and_orders_its_source_product():
    agent = ordering(TraderProviderAgent, "wholesaler", {"farms": 100.0},
                     storage_capacity=150.0, product="soybean")
    result = agent.step({"orders": [{"key": "santos", "quantity": 100.0, "product": "soybean"}],
                         "upstream": [arrived("farms", 100.0, "soybean")]})
    assert result["deliveries"] == [{"key": "santos", "quantity": 100.0, "product": "soybean"}]
    assert result["orders"] == [{"key": "farms", "quantity": 100.0, "product": "soybean"}]


def test_mill_orders_beans_and_delivers_meal():
    agent = ordering(ProcessProviderAgent, "processor", {"rotterdam": 100.0},
                     conversion_ratio=0.8, product="soybean_meal", input_product="soybean")
    result = agent.step({"orders": [{"key": "feed", "quantity": 80.0}],
                         "upstream": [arrived("rotterdam", 100.0, "soybean")]})
    assert result["deliveries"] == [{"key": "feed", "quantity": 80.0, "product": "soybean_meal"}]
    assert result["orders"] == [{"key": "rotterdam", "quantity": 100.0, "product": "soybean"}]


def test_transport_delivers_the_product_it_carries():
    agent = ordering(TransportProviderAgent, "sea_transport", {"santos": 100.0},
                     capacity=100.0, product="soybean")
    result = agent.step({"orders": [{"key": "rotterdam", "quantity": 100.0}],
                         "upstream": [arrived("santos", 100.0, "soybean")]})
    assert result["deliveries"] == [{"key": "rotterdam", "quantity": 100.0, "product": "soybean"}]
    assert result["orders"] == [{"key": "santos", "quantity": 100.0, "product": "soybean"}]


def test_order_for_another_product_is_rejected():
    agent = ordering(TraderProviderAgent, "feed_trader", {"mill": 100.0},
                     product="compound_feed")
    with pytest.raises(ValueError, match="'soybean'"):
        agent.step({"orders": [{"key": "pigs", "quantity": 10.0, "product": "soybean"}],
                    "upstream": [arrived("mill", 100.0)]})


@pytest.mark.parametrize("ordered", [True, False])
def test_mill_rejects_a_source_with_another_product(ordered):
    agent = ordering(ProcessProviderAgent, "processor", {"rotterdam": 100.0},
                     product="soybean_meal", input_product="soybean")
    data = {"upstream": [arrived("rotterdam", 100.0, "maize")], "peer_count": 1}
    if ordered:
        data["orders"] = [{"key": "feed", "quantity": 80.0}]
    with pytest.raises(ValueError, match="'maize'"):
        agent.step(data)


def test_without_products_records_stay_as_before():
    agent = ordering(TraderProviderAgent, "wholesaler", {"farms": 100.0},
                     storage_capacity=150.0)
    result = agent.step({"orders": [{"key": "santos", "quantity": 100.0, "product": "soybean"}],
                         "upstream": [arrived("farms", 100.0)]})
    assert result["deliveries"] == [{"key": "santos", "quantity": 100.0}]
    assert result["orders"] == [{"key": "farms", "quantity": 100.0}]
