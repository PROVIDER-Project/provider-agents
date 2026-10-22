"""Producer and livestock-consumer decisions, independent of the simulation."""

from typing import Any

import numpy as np

from ..abstract_provider_agent import AbstractPROVIDERAgent
from ._common import (
    SHARED_DEFAULTS,
    UPSTREAM,
    ObservationRequirements,
    effective,
    initialize,
    make_spec,
    snapshot,
    synchronize,
)

ROLE_PRODUCER = "producer"
ROLE_CONSUMER = "consumer"
CONSUMER_SOURCE_SCHEMA = {
    **UPSTREAM["items"],
    "required": ["key", "quantity_available", "unit_price", "recipient_count"],
}


class FarmerProviderAgent(ObservationRequirements, AbstractPROVIDERAgent):
    """Initialize with parameters; step with effects and per-source recipient counts."""

    observation_roles = (ROLE_PRODUCER, ROLE_CONSUMER)
    defaults = {
        **SHARED_DEFAULTS, "role": "", "fixed_costs": 0.0,
        "days_without_input": 0, "bankruptcy_threshold_days": 21,
        "base_yield": 0.0, "margin": 0.0, "feed_received": 0.0,
        "livestock_output": 0.0, "size_sigma": 0.0, "size_factor": 1.0,
    }
    spec = make_spec(
        "farmer", "Soy producer or livestock consumer; seeded size and bankruptcy state.",
        defaults,
        setup_extra={"farm_size_seed": {"type": "integer"}, "agent_id": {"type": "integer"}},
        patches=(("quantity_available", "unit_price"),
                 ("feed_received", "livestock_output", "days_without_input", "active")),
    )
    spec.step_input_schema["allOf"] = [{
        "if": {"required": ["state"], "properties": {"state": {
            "required": ["role"], "properties": {"role": {"const": ROLE_CONSUMER}},
        }}},
        "then": {"properties": {"upstream": {
            "type": "array", "items": CONSUMER_SOURCE_SCHEMA,
        }}},
    }]

    def _setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        initialize(self, data_in)
        self.size_factor = 1.0
        if self.size_sigma != 0.0:
            seed = data_in.get("farm_size_seed", 0) + data_in.get("agent_id", 0)
            rng = np.random.default_rng(seed)
            self.size_factor = float(rng.lognormal(mean=0.0, sigma=self.size_sigma))
        self.base_yield *= self.size_factor
        self.fixed_costs *= self.size_factor
        self.quantity_available = self.base_yield
        if self.quantity_available > 0:
            self.unit_price = (self.fixed_costs / self.quantity_available) * (1.0 + self.margin)
        return snapshot(self)

    def _step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        synchronize(self, data_in)
        if not self.active:
            return {}
        if self.role == ROLE_PRODUCER:
            self.quantity_available = self.base_yield * effective(data_in, "capacity")
            if self.quantity_available > 0:
                costs = self.fixed_costs * effective(data_in, "fertilizer")
                self.unit_price = (costs / self.quantity_available) * (1.0 + self.margin)
            else:
                self.unit_price = 0.0
            return {"quantity_available": self.quantity_available, "unit_price": self.unit_price}
        if self.role != ROLE_CONSUMER:
            raise ValueError(f"Farmer has unknown role: {self.role!r}")
        upstream = data_in.get("upstream", [])
        for source in upstream:
            if "recipient_count" not in source:
                raise ValueError("Consumer upstream source requires recipient_count")
        self.feed_received = sum(
            source["quantity_available"] / source["recipient_count"] for source in upstream
        )
        self.livestock_output = self.feed_received
        if self.feed_received == 0.0:
            self.days_without_input += 1
        else:
            self.days_without_input = 0
        if self.days_without_input >= self.bankruptcy_threshold_days:
            self.active = False
        return {name: getattr(self, name) for name in (
            "feed_received", "livestock_output", "days_without_input", "active",
        )}
