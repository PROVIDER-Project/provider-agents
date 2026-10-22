"""Transport capacity, route allocation, admission, and freight pricing."""

import math
from typing import Any

from ..abstract_provider_agent import AbstractPROVIDERAgent
from ._common import (
    NUMBER,
    SHARED_DEFAULTS,
    effective,
    initialize,
    make_spec,
    object_schema,
    snapshot,
    synchronize,
)

ROLE_LAND_TRANSPORT = "land_transport"
ROLE_SEA_TRANSPORT = "sea_transport"
ROUTE_SCHEMA = object_schema({
    "name": {"type": "string"}, "role": {"type": "string"},
    "is_transport": {"type": "boolean"},
    "entity_ids": {"type": "array", "items": {"type": "string"}},
}, ("name", "role", "is_transport", "entity_ids"))
UPDATE_SCHEMA = object_schema({
    "key": {"type": "string"}, "quantity_available": NUMBER, "utilisation": NUMBER,
}, ("key", "quantity_available"))


class TransportProviderAgent(AbstractPROVIDERAgent):
    """Select movement behavior from graph metadata and return explicit source patches."""

    defaults = {
        **SHARED_DEFAULTS, "role": "", "fixed_costs": 0.0, "capacity": 0.0,
        "utilisation": 0.0, "utilisation_threshold": 0.8, "transit_steps": 0,
        "margin_transport": 0.0,
    }
    spec = make_spec(
        "transport", "Land/sea transport with normalized exports and cheapest-first imports.",
        defaults,
        step_extra={
            "list_name": {"type": "string"},
            "adjacency": {"type": "object", "additionalProperties": {
                "type": "array", "items": {"type": "string"},
            }},
            "routes": {"type": "array", "items": ROUTE_SCHEMA},
            # Conversion/validation is intentionally deferred until an export
            # path reads the weight, preserving ignored-weight behavior.
            "route_weights": {"type": "object", "additionalProperties": {}},
        },
        output_extra={"upstream_updates": {"type": "array", "items": UPDATE_SCHEMA}},
        patches=(("quantity_available", "utilisation", "unit_price"),),
    )

    def _setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        initialize(self, data_in)
        self.quantity_available = self.capacity
        if self.capacity > 0:
            self.unit_price = (self.fixed_costs / self.capacity) * (1.0 + self.margin_transport)
        return snapshot(self)

    def _step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        synchronize(self, data_in)
        if not self.active:
            return {}
        if self.role == ROLE_SEA_TRANSPORT:
            return self._move(data_in)
        if self.role != ROLE_LAND_TRANSPORT:
            raise ValueError(f"Transport has unknown role: {self.role!r}")
        name = data_in.get("list_name", "")
        adjacency = data_in.get("adjacency", {})
        role_by_name = {route["name"]: route["role"] for route in data_in.get("routes", [])}
        feeds_sea = any(role_by_name.get(destination) == ROLE_SEA_TRANSPORT and name in sources
                        for destination, sources in adjacency.items())
        if feeds_sea:
            return self._move(data_in, share=self._route_share(data_in, name))
        if len(adjacency.get(name, ())) > 1:
            return self._admit_cheapest(data_in)
        return self._move(data_in)

    def _route_share(self, data, name):
        adjacency = data.get("adjacency", {})
        upstream_names = adjacency.get(name, ())
        routes = {
            route["name"]: route["entity_ids"][0]
            for route in data.get("routes", [])
            if route["is_transport"] and len(route["entity_ids"]) == 1
            and adjacency.get(route["name"], ()) == upstream_names
        }
        if name not in routes:
            raise ValueError(f"transport route {name!r} has no declared port entity")
        supplied = data.get("route_weights", {})
        explicit = {}
        unspecified = []
        for route_name, entity in routes.items():
            if entity not in supplied:
                unspecified.append(route_name)
                continue
            value = float(supplied[entity])
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"share_{entity} must be a finite non-negative route weight")
            explicit[route_name] = value
        if len(routes) == 1:
            return 1.0
        if not explicit:
            return 1.0 / len(routes)
        weights = dict(explicit)
        remaining = max(0.0, 1.0 - sum(explicit.values()))
        if unspecified:
            default = remaining / len(unspecified)
            weights.update({route_name: default for route_name in unspecified})
        total = sum(weights.values())
        if total <= 0.0:
            raise ValueError("route weights must have a positive total")
        return weights[name] / total

    def _result(self):
        return {"quantity_available": self.quantity_available,
                "utilisation": self.utilisation, "unit_price": self.unit_price}

    def _empty(self):
        self.quantity_available = self.utilisation = self.unit_price = 0.0
        return self._result()

    def _move(self, data, share=None):
        upstream = data.get("upstream", [])
        peers = data.get("peer_count", 0)
        if not upstream or peers == 0:
            return self._empty()
        total = sum(source["quantity_available"] for source in upstream)
        # Export splitting has this additional early return in the original.
        if share is not None and total <= 0.0:
            return self._empty()
        volume = total / peers if share is None else (total * share) / peers
        capacity = self.capacity * effective(data, "capacity")
        self.quantity_available = min(volume, capacity)
        self.utilisation = self.quantity_available / capacity if capacity > 0 else 0.0
        value = sum(source["unit_price"] * source["quantity_available"] for source in upstream)
        price = value / total if total > 0 else 0.0
        self._price(data, price)
        return self._result()

    def _price(self, data, upstream_price):
        if self.quantity_available > 0:
            costs = self.fixed_costs * effective(data, "energy")
            fee = (costs / self.quantity_available) * (1.0 + self.margin_transport)
            self.unit_price = upstream_price + fee
        else:
            self.unit_price = 0.0

    def _admit_cheapest(self, data):
        capacity = self.capacity * effective(data, "capacity")
        target = min(self.capacity, capacity)
        remaining = max(0.0, target)
        purchased_value = 0.0
        updates = []
        for source in sorted(data.get("upstream", []), key=lambda item: item["unit_price"]):
            admitted = min(max(0.0, source["quantity_available"]), remaining)
            update = {"key": source["key"], "quantity_available": admitted}
            if source.get("is_transport", False):
                source_capacity = source["capacity"] * effective(source, "capacity")
                update["utilisation"] = admitted / source_capacity if source_capacity > 0.0 else 0.0
            updates.append(update)
            purchased_value += source["unit_price"] * admitted
            remaining -= admitted
        purchased = target - remaining
        self.quantity_available = max(0.0, purchased)
        self.utilisation = self.quantity_available / capacity if capacity > 0.0 else 0.0
        upstream_price = (
            purchased_value / self.quantity_available if self.quantity_available > 0.0 else 0.0
        )
        self._price(data, upstream_price)
        return {**self._result(), "upstream_updates": updates}
