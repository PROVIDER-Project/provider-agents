"""Regional wholesaler and feed-distributor decisions."""

from typing import Any

from ..abstract_provider_agent import AbstractPROVIDERAgent
from ._common import (
    SHARED_DEFAULTS,
    UPSTREAM,
    ObservationRequirements,
    allocate,
    carried,
    initialize,
    make_spec,
    place_orders,
    received,
    snapshot,
    synchronize,
)
from .economics import operating_cost

ROLE_WHOLESALER = "wholesaler"
ROLE_FEED_TRADER = "feed_trader"
WHOLESALER_SOURCE_SCHEMA = {
    **UPSTREAM["items"],
    "required": ["key", "quantity_available", "unit_price", "base_yield"],
}


class TraderProviderAgent(ObservationRequirements, AbstractPROVIDERAgent):
    """Aggregate upstream supply and price it with overhead and margin."""

    observation_roles = (ROLE_WHOLESALER, ROLE_FEED_TRADER)
    defaults = {
        **SHARED_DEFAULTS, "role": "", "fixed_costs": 0.0,
        "markup": 0.0, "margin": 0.0, "stock": 0.0,
        "storage_capacity": 0.0, "storage_utilization": 0.0,
        "input_cost_shares": {},
        "baseline_orders": {}, "last_orders": {},
    }
    spec = make_spec(
        "trader", "Regional soy wholesaler or livestock feed distributor.", defaults,
        patches=(("stock", "quantity_available"),
                 ("stock", "quantity_available", "unit_price", "storage_utilization"),
                 ("stock", "quantity_available", "unit_price", "last_orders")),
    )
    spec.step_input_schema["allOf"] = [{
        "if": {"required": ["state"], "not": {"required": ["orders"]}, "properties": {"state": {
            "required": ["role"], "properties": {"role": {"const": ROLE_WHOLESALER}},
        }}},
        "then": {"properties": {"upstream": {
            "type": "array", "items": WHOLESALER_SOURCE_SCHEMA,
        }}},
    }]

    def _setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        initialize(self, data_in)
        self.markup = self.margin
        self.stock = self.quantity_available = self.unit_price = self.storage_utilization = 0.0
        return snapshot(self)

    def _step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        synchronize(self, data_in)
        if not self.active or self.role not in (ROLE_WHOLESALER, ROLE_FEED_TRADER):
            return {}
        if "orders" in data_in:
            return self._trade(data_in)
        carry = carried(self, data_in)
        upstream = data_in.get("upstream", [])
        peers = data_in.get("peer_count", 0)
        fields = ["stock", "quantity_available"]
        if not upstream or peers == 0:
            self.stock = self.quantity_available = carry
            if self.role == ROLE_WHOLESALER:
                if carry == 0:
                    self.unit_price = 0.0
                self.storage_utilization = (
                    carry / self.storage_capacity if self.storage_capacity > 0 else 0.0
                )
                fields += ["unit_price", "storage_utilization"]
            return {**{name: getattr(self, name) for name in fields},
                    "received": received(upstream, 0.0)}

        total = sum(source["quantity_available"] for source in upstream)
        if self.role == ROLE_WHOLESALER:
            # The schema cannot inspect a role retained from setup when state
            # is omitted, so enforce its role-specific requirement here too.
            for source in upstream:
                if "base_yield" not in source:
                    raise ValueError("Wholesaler upstream source requires base_yield")
            normal = sum(source["base_yield"] for source in upstream)
            normal_share = normal / peers
            current_share = total / peers
            demand = min(max(normal_share, current_share), self.storage_capacity)
            taken = min(current_share, demand, max(0.0, self.storage_capacity - carry))
            self.stock = carry + taken
            self.storage_utilization = (
                self.stock / self.storage_capacity if self.storage_capacity > 0 else 0.0
            )
            fields.append("storage_utilization")
        else:
            taken = total / peers
            self.stock = carry + taken
        self.quantity_available = self.stock
        total_value = sum(
            source["unit_price"] * source["quantity_available"] for source in upstream
        )
        avg_price = total_value / total if total > 0 else 0.0
        if taken > 0:
            overhead = operating_cost(self.fixed_costs, self.input_cost_shares,
                                      data_in.get("effects", {}))
            cost = avg_price + overhead / taken
            self.unit_price = cost * (1.0 + self.margin)
        elif self.stock == 0:
            self.unit_price = 0.0
        fields.append("unit_price")
        return {**{name: getattr(self, name) for name in fields},
                "received": received(upstream, taken)}

    def _trade(self, data_in):
        upstream = data_in.get("upstream", [])
        taken = sum(source.get("delivered", 0.0) for source in upstream)
        self.stock = self.quantity_available = carried(self, data_in) + taken
        deliveries = allocate(data_in["orders"], self.stock)
        left = self.stock - sum(entry["quantity"] for entry in deliveries)
        fields = ["stock", "quantity_available", "unit_price", "last_orders"]
        limit = None
        if self.role == ROLE_WHOLESALER:
            self.storage_utilization = (
                self.stock / self.storage_capacity if self.storage_capacity > 0 else 0.0
            )
            limit = self.storage_capacity - left
            fields.append("storage_utilization")
        if taken > 0:
            value = sum(source["unit_price"] * source.get("delivered", 0.0)
                        for source in upstream)
            overhead = operating_cost(self.fixed_costs, self.input_cost_shares,
                                      data_in.get("effects", {}))
            self.unit_price = (value / taken + overhead / taken) * (1.0 + self.margin)
        elif self.stock == 0:
            self.unit_price = 0.0
        orders = place_orders(upstream, self.baseline_orders, self.last_orders, limit)
        self.last_orders = {order["key"]: order["quantity"] for order in orders}
        return {**{name: getattr(self, name) for name in fields},
                "deliveries": deliveries, "orders": orders}
