"""Input conversion and pricing for crushers and feed manufacturers."""

from typing import Any

from ..abstract_provider_agent import AbstractPROVIDERAgent
from ._common import (
    SHARED_DEFAULTS,
    ObservationRequirements,
    effective,
    initialize,
    make_spec,
    received,
    snapshot,
    synchronize,
)
from .economics import nonnegative, operating_cost

ROLE_PROCESSOR = "processor"
ROLE_FEED_MANUFACTURER = "feed_manufacturer"


class ProcessProviderAgent(ObservationRequirements, AbstractPROVIDERAgent):
    """Split upstream input over active peers, convert, and price output."""

    observation_roles = (ROLE_PROCESSOR, ROLE_FEED_MANUFACTURER)
    defaults = {
        **SHARED_DEFAULTS, "role": "", "fixed_costs": 0.0,
        "margin": 0.0, "input_received": 0.0, "conversion_ratio": 1.0,
        "input_cost_shares": {}, "throughput_capacity": None,
        "input_processed": 0.0, "unused_input": 0.0,
    }
    spec = make_spec(
        "process", "Crusher or feed manufacturer with capacity effects.", defaults,
        patches=(("input_received", "input_processed", "unused_input",
                  "quantity_available", "unit_price"),),
    )

    def _setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        initialize(self, data_in)
        self._validate_processing()
        self.input_received = 0.0
        self.input_processed = self.unused_input = 0.0
        self.quantity_available = 0.0
        self.unit_price = 0.0
        return snapshot(self)

    def _step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        synchronize(self, data_in)
        if not self.active or self.role not in (ROLE_PROCESSOR, ROLE_FEED_MANUFACTURER):
            return {}
        self._validate_processing()
        upstream = data_in.get("upstream", [])
        peers = data_in.get("peer_count", 0)
        if isinstance(peers, bool) or not isinstance(peers, int) or peers < 0:
            raise ValueError("peer_count must be a non-negative integer")
        factor = nonnegative(effective(data_in, "capacity"), "effects.capacity")
        for source in upstream:
            for name in ("quantity_available", "unit_price"):
                nonnegative(source[name], f"upstream.{name}")
        if not upstream or peers == 0:
            self.input_received = 0.0
            self.input_processed = self.unused_input = 0.0
            self.quantity_available = 0.0
            self.unit_price = 0.0
        else:
            total_input = sum(source["quantity_available"] for source in upstream)
            self.input_received = total_input / peers
            capacity = (self.input_received if self.throughput_capacity is None
                        else self.throughput_capacity)
            self.input_processed = min(self.input_received, capacity * factor)
            self.unused_input = self.input_received - self.input_processed
            self.quantity_available = self.input_processed * self.conversion_ratio
            total_value = sum(
                source["unit_price"] * source["quantity_available"] for source in upstream
            )
            avg_price = total_value / total_input if total_input > 0 else 0.0
            if self.quantity_available > 0:
                input_cost = avg_price / self.conversion_ratio
                overhead = operating_cost(self.fixed_costs, self.input_cost_shares,
                                          data_in.get("effects", {}))
                fixed_cost = overhead / self.quantity_available
                self.unit_price = (input_cost + fixed_cost) * (1.0 + self.margin)
            else:
                self.unit_price = 0.0
        return {**{name: getattr(self, name) for name in (
            "input_received", "input_processed", "unused_input", "quantity_available", "unit_price",
        )}, "received": received(upstream, self.input_received)}

    def _validate_processing(self):
        if nonnegative(self.conversion_ratio, "conversion_ratio") == 0:
            raise ValueError("conversion_ratio must be strictly positive")
        if self.throughput_capacity is not None:
            nonnegative(self.throughput_capacity, "throughput_capacity")
