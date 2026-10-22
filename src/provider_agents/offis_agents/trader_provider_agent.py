"""Regional wholesaler and feed-distributor decisions."""

from typing import Any

from ..abstract_provider_agent import AbstractPROVIDERAgent
from ._common import SHARED_DEFAULTS, initialize, make_spec, snapshot, synchronize

ROLE_WHOLESALER = "wholesaler"
ROLE_FEED_TRADER = "feed_trader"


class TraderProviderAgent(AbstractPROVIDERAgent):
    """Aggregate upstream supply and price it with overhead and margin."""

    defaults = {
        **SHARED_DEFAULTS, "role": "", "fixed_costs": 0.0,
        "markup": 0.0, "margin": 0.0, "stock": 0.0,
        "storage_capacity": 0.0, "storage_utilization": 0.0,
    }
    spec = make_spec("trader", "Regional soy wholesaler or livestock feed distributor.", defaults)

    def _setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        initialize(self, data_in)
        self.markup = self.margin
        self.stock = self.quantity_available = self.unit_price = self.storage_utilization = 0.0
        return snapshot(self)

    def _step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        synchronize(self, data_in)
        if not self.active or self.role not in (ROLE_WHOLESALER, ROLE_FEED_TRADER):
            return {}
        upstream = data_in.get("upstream", [])
        peers = data_in.get("peer_count", 0)
        fields = ["stock", "quantity_available"]
        if not upstream or peers == 0:
            self.stock = self.quantity_available = 0.0
            if self.role == ROLE_WHOLESALER:
                self.unit_price = self.storage_utilization = 0.0
                fields += ["unit_price", "storage_utilization"]
            return {name: getattr(self, name) for name in fields}

        total = sum(source["quantity_available"] for source in upstream)
        if self.role == ROLE_WHOLESALER:
            normal = sum(source["base_yield"] for source in upstream)
            normal_share = normal / peers
            current_share = total / peers
            demand = min(max(normal_share, current_share), self.storage_capacity)
            self.stock = min(current_share, demand)
            self.storage_utilization = self.stock / self.storage_capacity if self.storage_capacity > 0 else 0.0
            fields.append("storage_utilization")
        else:
            self.stock = total / peers
        self.quantity_available = self.stock
        total_value = sum(source["unit_price"] * source["quantity_available"] for source in upstream)
        avg_price = total_value / total if total > 0 else 0.0
        if self.stock > 0:
            cost = avg_price + self.fixed_costs / self.stock
            self.unit_price = cost * (1.0 + self.margin)
        else:
            self.unit_price = 0.0
        fields.append("unit_price")
        return {name: getattr(self, name) for name in fields}
