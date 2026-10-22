# provider-agents

Standalone supply-chain actors implementing `AbstractPROVIDERAgent`.
Python **3.10+** and NumPy are required. Melodie and provider-simenv are
not dependencies.

```bash
pip install .
# Development and full JSON Schema validation tests:
pip install -e '.[dev]'
pytest
ruff check .
```

## Implementations

Import the OFFIS implementations from `provider_agents.offis_agents`:

| Class | Roles | Decisions |
| --- | --- | --- |
| `FarmerProviderAgent` | `producer`, `consumer` | Seeded farm size, production, cost-based prices, feed sharing, bankruptcy |
| `TraderProviderAgent` | `wholesaler`, `feed_trader` | Aggregation, storage limits, input-weighted pricing |
| `ProcessProviderAgent` | `processor`, `feed_manufacturer` | Equal input sharing, conversion, capacity effects, pricing |
| `TransportProviderAgent` | `land_transport`, `sea_transport` | Export shares, capacity, cheapest-first import admission, freight prices |

These implementations preserve the original simenv decision rules, including
NumPy's seeded size draws, arithmetic order, early-return state patches, and
transport updates to upstream quantities/utilisation. `transit_steps` is
preserved state; it does not introduce delayed delivery.

## Public contract

Every class declares `spec: AgentSpec` (contract version `1.0`) containing
`setup_input_schema`, `setup_output_schema`, `step_input_schema`, and
`step_output_schema`. Always invoke the public `setup(dict)` and `step(dict)`
methods; they validate input/output around `_setup` and `_step`.

With optional `jsonschema` installed, messages receive full JSON Schema
validation. Otherwise the interface's built-in fallback performs only its
documented minimal checks, including required fields, ranges, and enums.
Do not rely on that fallback for complete type or nested-array validation.

```python
from provider_agents.offis_agents import FarmerProviderAgent

farmer = FarmerProviderAgent()
initial_state = farmer.setup({
    "role": "producer", "base_yield": 100.0,
    "fixed_costs": 200.0, "margin": 0.1,
    "size_sigma": 0.0, "farm_size_seed": 42, "agent_id": 3,
})
assert initial_state["unit_price"] == 2.2
actions = farmer.step({"effects": {"capacity": 0.5, "fertilizer": 1.2}})
assert actions == {"quantity_available": 50.0, "unit_price": 5.28}
```

### Setup and defaults

Setup inputs and outputs are flat mappings of behavioral state. Parameters
default to the values exposed in each class's `defaults` mapping and schema.
All agents begin active, with zero quantity and price before derived setup;
role defaults to the empty string for frameworks that assign parameters in
two phases. `setup({})` exposes those initialized fields; call setup again
with the assigned parameters before running steps. Do not reinitialize each
step or pass already-scaled farm costs/yields back through setup.

- Farmer: `role`, `active`, `base_yield`, `fixed_costs`, `margin`,
  `size_sigma`, `farm_size_seed`, `agent_id`, `days_without_input`,
  `bankruptcy_threshold_days`, `feed_received`, `livestock_output`.
  Size sigma defaults to 0, threshold to 21 days; yield and costs are scaled
  once during initialization. Output also includes `size_factor` (default 1).
- Trader: `role`, `active`, `fixed_costs`, `margin`, `storage_capacity`.
  Setup resets stock, price, quantity and storage utilisation to 0 and
  derives `markup` from margin.
- Process: `role`, `active`, `fixed_costs`, `margin`, `conversion_ratio`
  (default 1). Setup resets input received, quantity and price to 0.
- Transport: `role`, `active`, `fixed_costs`, `capacity`, `margin_transport`,
  `utilisation`, `utilisation_threshold` (default 0.8), `transit_steps`
  (default 0). Starts at full capacity with the initial freight fee.

Setup returns all behavioral fields for publishing into a host framework.
PDL bindings, entity origins, framework object references and list membership
belong to the host, not these agents.

### Step inputs

All step keys are optional; omit unavailable sources rather than passing
live framework objects. Defaults are empty source lists, zero peer/consumer
counts and neutral effects.

- `state`: current behavioral fields that the host has changed externally.
  Synchronize these before each step if the host also exposes mutable
  state. This is particularly important after downstream admission changes
  an upstream agent's quantity/utilisation or after activity changes.
- `effects`: semantic multiplier mapping (`capacity`, `fertilizer`,
  `energy`); absent slots default to 1.0. The host resolves PDL bindings.
- `upstream`: ordered source records with `key` (step-local unique string),
  `quantity_available`, `unit_price`. Include only active sources.
  Wholesaler source records also need `base_yield`. Transport sources
  include `is_transport: True`, `capacity`, and their own resolved `effects`
  when admission must update their utilisation.
- `peer_count`: active agents sharing this upstream input. Used by traders,
  processors, and ordinary/split transport movement.
- `consumer_count`: all active livestock consumers sharing feed.

Transport additionally accepts:

- `list_name`: current route's name.
- `adjacency`: route/list name to ordered upstream list names.
- `routes`: records with `name`, `role`, `is_transport` (whether the host
  archetype uses the transport class), and `entity_ids` (list of strings).
- `route_weights`: entity id to explicitly supplied route weight. Omit
  unspecified weights. The agent validates and normalizes applicable weights
  and selects export splitting, ordinary movement, or multi-source import
  admission from the graph. Weights must convert to finite non-negative
  numbers; multiple zero weights with zero total are rejected.

### Step outputs and upstream effects

Outputs are **patches**, not complete state snapshots. Apply only returned
fields; inactive agents return `{}`. Producers update quantity and price;
consumers update feed, livestock output, starvation days and activity;
processes update input, quantity and price. Traders update stock and
quantity, plus price/storage utilisation on the applicable paths. A feed
trader with no inputs deliberately leaves its previous price untouched.

Transport returns quantity, price, utilisation, and, on cheapest-first
admission, `upstream_updates`:

```python
{
    "quantity_available": 100.0,
    "utilisation": 1.0,
    "unit_price": 1.4,
    "upstream_updates": [
        {"key": "cheap", "quantity_available": 60.0, "utilisation": 0.6},
        {"key": "other", "quantity_available": 40.0},
    ],
}
```

Map keys back to the original sources and apply their patches in the same
step. Source prices are untouched; inputs are never mutated. Preserve source
order: tied prices use stable sorting. These keys must be unique within a
call, even if host agent ids repeat in different lists. Strip the
`upstream_updates` action before applying local state. Synchronize external
changes through `state` on the affected agent's next step.

Farmer and transport reject unknown active roles. Trader and process retain
their original unknown-role no-op behavior. Route-weight errors propagate
to the caller. There is no dependency on the illustrative farmer that
preceded these migrated implementations.
