"""Input conversion and pricing for crushers and feed manufacturers."""

from typing import Any

from ..abstract_provider_agent import AbstractPROVIDERAgent
from ._common import SHARED_DEFAULTS, effective, initialize, make_spec, snapshot, synchronize

ROLE_PROCESSOR = "processor"
ROLE_FEED_MANUFACTURER = "feed_manufacturer"


class ProcessProviderAgent(AbstractPROVIDERAgent):
    """Split upstream input over active peers, convert, and price output."""

    defaults = {
        **SHARED_DEFAULTS, "role": "", "fixed_costs": 0.0,
        "margin": 0.0, "input_received": 0.0, "conversion_ratio": 1.0,
    }
    spec = make_spec(
        "process", "Crusher or feed manufacturer with capacity effects.", defaults,
        patches=(("input_received", "quantity_available", "unit_price"),),
    )

    def _setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        initialize(self, data_in)
        self.input_received = 0.0
        self.quantity_available = 0.0
        self.unit_price = 0.0
        return snapshot(self)

    def _step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        synchronize(self, data_in)
        if not self.active or self.role not in (ROLE_PROCESSOR, ROLE_FEED_MANUFACTURER):
            return {}
        upstream = data_in.get("upstream", [])
        peers = data_in.get("peer_count", 0)
        if not upstream or peers == 0:
            self.input_received = 0.0
            self.quantity_available = 0.0
            self.unit_price = 0.0
        else:
            factor = effective(data_in, "capacity")
            total_input = sum(source["quantity_available"] for source in upstream)
            self.input_received = total_input / peers
            self.quantity_available = self.input_received * self.conversion_ratio * factor
            total_value = sum(
                source["unit_price"] * source["quantity_available"] for source in upstream
            )
            avg_price = total_value / total_input if total_input > 0 else 0.0
            if self.quantity_available > 0:
                input_cost = avg_price / self.conversion_ratio
                fixed_cost = self.fixed_costs / self.quantity_available
                self.unit_price = (input_cost + fixed_cost) * (1.0 + self.margin)
            else:
                self.unit_price = 0.0
        return {name: getattr(self, name) for name in (
            "input_received", "quantity_available", "unit_price",
        )}
