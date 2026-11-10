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

These implementations build on the original simenv decision rules, including
NumPy's seeded size draws, arithmetic order, early-return state patches, and
transport updates to upstream quantities/utilisation. `transit_steps` is
preserved state; it does not introduce delayed delivery.

OFFIS contract **2.0** adds selective operating-cost exposures and explicit
processing throughput, processed-input and unused-offer diagnostics. See
[Economic models and research](docs/economic-models.md) for equations,
scientific citations, assumptions, limitations and migration instructions.

OFFIS contract **3.0** adds deliveries, carried stock and orders. See
[Orders and deliveries](#orders-and-deliveries) for the fields and for what a
host has to change.

## Public contract

Every class declares `spec: AgentSpec` (OFFIS contract version `3.0`) containing
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
  (strictly positive, default 1), `throughput_capacity` (input units/step,
  default null). Setup resets input offered/processed/unused, quantity and
  price to 0.
- Transport: `role`, `active`, `fixed_costs`, `capacity`, `margin_transport`,
  `utilisation`, `utilisation_threshold` (default 0.8), `transit_steps`
  (default 0). Starts at full capacity with the initial freight fee.

All actors also expose `input_cost_shares`: semantic effect slot to baseline
operating-cost share, finite nonnegative with total<=1. Defaults preserve
fertilizer=1 for farmers, energy=1 for transport and no exposure for other
actors. These are illustrative compatibility assumptions; supply measured
shares to calibrate. `{}` disables exposure; absent effects remain neutral.

Setup returns all behavioral fields for publishing into a host framework.
PDL bindings, entity origins, framework object references and list membership
belong to the host, not these agents.

### Step inputs

All step keys are optional; omit unavailable sources rather than passing
live framework objects. Defaults are empty source lists, zero peer counts
and neutral effects. Consumer source records require their own recipient counts.

- `state`: current behavioral fields that the host has changed externally.
  Synchronize these before each step if the host also exposes mutable
  state. This is particularly important after downstream admission changes
  an upstream agent's quantity/utilisation or after activity changes.
- `effects`: semantic multiplier mapping (`capacity`, `fertilizer`,
  `energy`); absent slots default to 1.0. The host resolves PDL bindings.
- `upstream`: ordered source records with `key` (unique string),
  `quantity_available`, `unit_price`. Include only active sources.
  Wholesaler source records also need `base_yield`. Consumer source records
  need `recipient_count`, the active recipients of that individual feed
  trader. Each source's feed is divided by its own count, then summed.
  Transport sources
  include `is_transport: True`, `capacity`, and their own resolved `effects`
  when admission must update their utilisation.
- `peer_count`: active agents sharing this upstream input. Used by traders,
  processors, and ordinary/split transport movement.

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
processes update offered `input_received`, actual `input_processed`,
`unused_input`, quantity and price. Without `shipped`, unused offers are not
inventories or settled purchases. Traders update stock and
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

### Orders and deliveries

An agent works in one of two ways, decided per step by its input.

- Without `orders` in the step input it uses the take rules described above.
  It reads what its sources offer and takes its share.
- With `orders` in the step input (an empty list for an agent nobody orders
  from) it ships what its buyers ordered and orders from its own sources.

Additional step input:

- `shipped`: what buyers took from this agent in the previous step. With it,
  producers, traders and processes keep what was not taken as `stock`.
  Omit it on the first step.
- `orders`: records with `key` (the buyer) and `quantity`, what each buyer
  ordered from this agent in the previous step.
- On each `upstream` record: `delivered`, what that source delivered to this
  agent in the current step, and `spare`, what the source still holds after
  its deliveries.

Additional step output:

- `received` (take rules only): records with `key` and `quantity`, what the
  agent took from each source.
- `deliveries` (on orders): records with `key` (the buyer) and `quantity`.
  Every order is filled in full, or all are scaled by the same factor when
  the agent is short.
- `orders` (on orders): records with `key` (the source) and `quantity` for
  the next step.

Additional state: `stock`, `baseline_orders` and `last_orders` (source key to
quantity). A buyer orders its baseline from each source. What a source left
unfilled in the previous step is moved to the other sources that report
`spare`, and whatever no source holds is dropped. The total is capped by what
the buyer can take: throughput for processes, free storage for wholesalers,
the baseline need for consumers and capacity for transports. Feed traders
have no cap.

On orders a consumer uses at most its baseline need per step and keeps the
rest as `stock`. `feed_received` is what arrived and `livestock_output` what
was used. A transport passes on everything that arrives and forwards the sum
of its buyers' orders to its own sources. `peer_count`, `recipient_count`,
wholesaler `base_yield` on source records, `route_weights` and
`upstream_updates` belong to the take rules and are not used on orders.

What a host has to do to run on orders:

1. Use source and buyer keys that stay the same across steps.
   `baseline_orders` and `last_orders` are stored under them.
2. Set `baseline_orders` and `last_orders` on every buyer before the first
   step. An agent without a baseline orders nothing.
3. Pass each agent the previous step's `orders` from its buyers, and
   `delivered` and `spare` on its source records.
4. Book the returned `deliveries` and hand the returned `orders` to the
   sources in the next step.
5. Strip `received`, `deliveries` and `orders` before applying the returned
   patch to local state.

### Optional host observation helper

`agent.requires_observations(state)` reports whether the current activity
and role need host observations. A host can skip model/graph queries when
this returns false, and call the regular validated `step({"state": state})`
to obtain the original no-op or unknown-role error. The helper never mutates
state; role/activity decisions remain in the standalone implementation.

The source schemas require `capacity` when `is_transport` is true. Trader's
step schema additionally requires `base_yield` for upstream records when
`state.role` is `wholesaler`; when the role is retained from setup and not
repeated in the message, execution enforces that same requirement explicitly.
Farmer's consumer source records similarly require `recipient_count` in the
role-aware schema and during execution when the role is retained from setup.
