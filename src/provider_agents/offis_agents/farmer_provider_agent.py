"""Standalone farmer agent implementing the PROVIDER agent interface.

Input and output contract
=========================

`setup(data_in)` input keys:
- `role` (`str`, required): either `"producer"` or `"consumer"`.
- `fixed_costs` (`float`, optional): operating cost per step.
- `days_without_input` (`int`, optional): current consecutive zero-input count.
- `bankruptcy_threshold_days` (`int`, optional): zero-input limit before exit.
- `base_yield` (`float`, optional): baseline producer output before shocks.
- `margin` (`float`, optional): markup ratio on top of cost.
- `feed_received` (`float`, optional): consumer feed already on hand.
- `livestock_output` (`float`, optional): consumer output already on hand.
- `size_sigma` (`float`, optional): log-normal dispersion for agent size.
- `farm_size_seed` (`int`, optional): seed used for reproducible size sampling.
- `agent_id` (`int`, optional): unique agent id used with `farm_size_seed`.
- `binding` (`dict[str, tuple[str, str]]`, optional): semantic shock bindings.
- `origin` (`str`, optional): source entity id.
- `active` (`bool`, optional): initial market status.

`setup(data_in)` output keys:
Returns every state field changed by setup, including derived values that were
handled by `post_setup()` in the original farmer implementation:
- `quantity_available`
- `unit_price`
- `active`
- `origin`
- `binding`
- `role`
- `fixed_costs`
- `days_without_input`
- `bankruptcy_threshold_days`
- `base_yield`
- `margin`
- `feed_received`
- `livestock_output`
- `size_sigma`
- `size_factor`

`step(data_in)` input keys:
- `effects` (`dict[str, float]`, optional): resolved effect multipliers by
  semantic slot, for example `{"capacity": 0.8, "fertilizer": 1.2}`.
  Missing slots default to `1.0`.
- `active_eu_farmers_count` (`int`, optional): number of active EU farmers.
  Required for consumer behavior.
- `upstream_feed_quantities` (`list[float]`, optional): quantity available from
  each upstream feed trader. Used for consumer behavior.

`step(data_in)` output keys:
Returns every state field changed by the selected step path.
Producer output:
- `quantity_available`
- `unit_price`

Consumer output:
- `feed_received`
- `livestock_output`
- `days_without_input`
- `active`
"""

from __future__ import annotations

from math import exp
from random import Random
from builtins import bool, dict, float, int, list, str, tuple
from typing import Any, NotRequired, TypedDict

from ..abstract_provider_agent import AbstractPROVIDERAgent, AgentSpec

ROLE_PRODUCER = "producer"
ROLE_CONSUMER = "consumer"


class SetupInput(TypedDict, total=False):
    role: str
    fixed_costs: float
    days_without_input: int
    bankruptcy_threshold_days: int
    base_yield: float
    margin: float
    feed_received: float
    livestock_output: float
    size_sigma: float
    farm_size_seed: int
    agent_id: int
    binding: dict[str, tuple[str, str]]
    origin: str
    active: bool


class SetupOutput(TypedDict):
    quantity_available: float
    unit_price: float
    active: bool
    origin: str
    binding: dict[str, tuple[str, str]]
    role: str
    fixed_costs: float
    days_without_input: int
    bankruptcy_threshold_days: int
    base_yield: float
    margin: float
    feed_received: float
    livestock_output: float
    size_sigma: float
    size_factor: float


class StepInput(TypedDict, total=False):
    effects: dict[str, float]
    active_eu_farmers_count: NotRequired[int]
    upstream_feed_quantities: NotRequired[list[float]]


class ProducerStepOutput(TypedDict):
    quantity_available: float
    unit_price: float


class ConsumerStepOutput(TypedDict):
    feed_received: float
    livestock_output: float
    days_without_input: int
    active: bool


FARMER_SPEC = AgentSpec(
    agent_id="farmer",
    contract_version="1.0",
    description="Producer/consumer farmer agent (see module docstring for full field list)",
    setup_input_schema={
        "type": "object",
        "properties": {
            "role": {"type": "string", "enum": [ROLE_PRODUCER, ROLE_CONSUMER]},
            "fixed_costs": {"type": "number", "minimum": 0},
            "days_without_input": {"type": "integer", "minimum": 0},
            "bankruptcy_threshold_days": {"type": "integer", "minimum": 0},
            "base_yield": {"type": "number", "minimum": 0},
            "margin": {"type": "number"},
            "feed_received": {"type": "number", "minimum": 0},
            "livestock_output": {"type": "number", "minimum": 0},
            "size_sigma": {"type": "number", "minimum": 0},
            "farm_size_seed": {"type": "integer"},
            "agent_id": {"type": "integer"},
            "binding": {"type": "object"},
            "origin": {"type": "string"},
            "active": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
    setup_output_schema={
        "type": "object",
        "required": [
            "quantity_available",
            "unit_price",
            "active",
            "origin",
            "binding",
            "role",
            "fixed_costs",
            "days_without_input",
            "bankruptcy_threshold_days",
            "base_yield",
            "margin",
            "feed_received",
            "livestock_output",
            "size_sigma",
            "size_factor",
        ],
        "properties": {
            "quantity_available": {"type": "number", "minimum": 0},
            "unit_price": {"type": "number", "minimum": 0},
            "active": {"type": "boolean"},
            "origin": {"type": "string"},
            "binding": {"type": "object"},
            "role": {"type": "string"},
            "fixed_costs": {"type": "number"},
            "days_without_input": {"type": "integer"},
            "bankruptcy_threshold_days": {"type": "integer"},
            "base_yield": {"type": "number"},
            "margin": {"type": "number"},
            "feed_received": {"type": "number"},
            "livestock_output": {"type": "number"},
            "size_sigma": {"type": "number"},
            "size_factor": {"type": "number"},
        },
        "additionalProperties": False,
    },
    step_input_schema={
        "type": "object",
        "properties": {
            "effects": {"type": "object"},
            "active_eu_farmers_count": {"type": "integer", "minimum": 0},
            "upstream_feed_quantities": {"type": "array"},
        },
        "additionalProperties": False,
    },
    step_output_schema={
        "type": "object",
        "properties": {
            "quantity_available": {"type": "number", "minimum": 0},
            "unit_price": {"type": "number", "minimum": 0},
            "feed_received": {"type": "number", "minimum": 0},
            "livestock_output": {"type": "number", "minimum": 0},
            "days_without_input": {"type": "integer", "minimum": 0},
            "active": {"type": "boolean"},
        },
        "additionalProperties": False,
    },
)


class FarmerProviderAgent(AbstractPROVIDERAgent):
    """Farmer agent with explicit dict-based inputs and outputs."""

    spec = FARMER_SPEC

    def _setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        setup_input: SetupInput = data_in

        self.quantity_available = 0.0
        self.unit_price = 0.0
        self.active = setup_input.get("active", True)
        self.origin = setup_input.get("origin", "")
        self.binding = setup_input.get("binding", {})

        self.role = setup_input.get("role", "")
        self.fixed_costs = setup_input.get("fixed_costs", 0.0)
        self.days_without_input = setup_input.get("days_without_input", 0)
        self.bankruptcy_threshold_days = setup_input.get(
            "bankruptcy_threshold_days", 21
        )
        self.base_yield = setup_input.get("base_yield", 0.0)
        self.margin = setup_input.get("margin", 0.0)
        self.feed_received = setup_input.get("feed_received", 0.0)
        self.livestock_output = setup_input.get("livestock_output", 0.0)
        self.size_sigma = setup_input.get("size_sigma", 0.0)

        farm_size_seed = setup_input.get("farm_size_seed", 0)
        agent_id = setup_input.get("agent_id", 0)
        self.size_factor = self._sample_size_factor(self.size_sigma, farm_size_seed, agent_id)

        self.base_yield *= self.size_factor
        self.fixed_costs *= self.size_factor
        self.quantity_available = self.base_yield

        if self.quantity_available > 0:
            self.unit_price = (
                self.fixed_costs / self.quantity_available
            ) * (1.0 + self.margin)

        return SetupOutput(
            quantity_available=self.quantity_available,
            unit_price=self.unit_price,
            active=self.active,
            origin=self.origin,
            binding=self.binding,
            role=self.role,
            fixed_costs=self.fixed_costs,
            days_without_input=self.days_without_input,
            bankruptcy_threshold_days=self.bankruptcy_threshold_days,
            base_yield=self.base_yield,
            margin=self.margin,
            feed_received=self.feed_received,
            livestock_output=self.livestock_output,
            size_sigma=self.size_sigma,
            size_factor=self.size_factor,
        )

    def _step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        step_input: StepInput = data_in

        if not self.active:
            return {}
        if self.role == ROLE_CONSUMER:
            return self._step_consumer(step_input)
        if self.role == ROLE_PRODUCER:
            return self._step_producer(step_input)
        raise ValueError(f"Farmer has unknown role: {self.role!r}")

    def _sample_size_factor(self, sigma: float, farm_size_seed: int, agent_id: int) -> float:
        """Sample a reproducible log-normal size factor centered at 1.0."""
        if sigma == 0.0:
            return 1.0
        rng = Random(farm_size_seed + agent_id)
        return exp(rng.gauss(0.0, sigma))

    def _effective(self, data_in: StepInput, slot: str) -> float:
        effects = data_in.get("effects", {})
        return effects.get(slot, 1.0)

    def _step_producer(self, data_in: StepInput) -> ProducerStepOutput:
        capacity = self._effective(data_in, "capacity")
        self.quantity_available = self.base_yield * capacity

        if self.quantity_available > 0:
            effective_costs = self.fixed_costs * self._effective(data_in, "fertilizer")
            self.unit_price = (
                effective_costs / self.quantity_available
            ) * (1.0 + self.margin)
        else:
            self.unit_price = 0.0

        return ProducerStepOutput(
            quantity_available=self.quantity_available,
            unit_price=self.unit_price,
        )

    def _step_consumer(self, data_in: StepInput) -> ConsumerStepOutput:
        active_eu_farmers_count = data_in.get("active_eu_farmers_count", 0)
        upstream_feed_quantities = data_in.get("upstream_feed_quantities", [])
        total_feed = sum(upstream_feed_quantities)
        self.feed_received = (
            total_feed / active_eu_farmers_count if active_eu_farmers_count > 0 else 0.0
        )

        self.livestock_output = self.feed_received

        if self.feed_received == 0.0:
            self.days_without_input += 1
        else:
            self.days_without_input = 0

        if self.days_without_input >= self.bankruptcy_threshold_days:
            self.active = False

        return ConsumerStepOutput(
            feed_received=self.feed_received,
            livestock_output=self.livestock_output,
            days_without_input=self.days_without_input,
            active=self.active,
        )
