# OFFIS economic models and research assessment

Research for [provider-agents #3](https://github.com/PROVIDER-Project/provider-agents/issues/3)
and [simenv #71](https://github.com/PROVIDER-Project/simenv/issues/71),
reviewed 2 November 2026. This document describes OFFIS contract **2.0**.

## Conclusion

Retain a transparent, short-run, fixed-technology production network. Add
explicit cost exposures and distinguish processing throughput from conversion
yield before introducing more elaborate adaptive behavior. These changes improve
**structural fidelity and configurability**. Neither published mechanisms nor
accounting identities establish that the illustrative soybean scenario predicts
actual prices, quantities or recovery times. That requires calibration and
held-out observations.

The research supports retaining the framework-independent decision policies:
network effects depend on actual supplier relationships [1–4], so relationships
must remain host/scenario inputs. Model equations must not name countries,
ports or individual entities. No coefficients below are estimated from the cited
papers; numerical examples are synthetic, hand-checkable illustrations.

## Existing-model audit

| Actor/mechanism | Existing assumption | Assessment and action |
| --- | --- | --- |
| Producer | Exogenous daily yield; costs divided by output; fertilizer reprices the entire cost base | Useful short-run supply-shock baseline. Introduce configurable expenditure shares instead of requiring 100% fertilizer exposure. No endogenous acreage/yield response without agronomic and seasonal data. |
| Wholesaler/feed trader | Same-tick aggregation, handling/storage cap, weighted upstream price plus overhead and markup | Keep the aggregation/quotation rule. `stock` is current throughput, not carried inventory; it cannot buffer a delivery interruption. Add selective operating-cost exposures. |
| Processor/feed manufacturer | Equal input shares; yield multiplied by a capacity effect; no explicit unused-input accounting | Add an absolute input throughput constraint, preserve a documented proportional fallback, distinguish offers from processed material, and price only processed input. |
| Transport | Fixed route weights, capacity limits, cheapest-first multi-source admission and cost-plus freight | Keep these transparent rules with selective cost exposure. No endogenous rerouting, shipment settlement, or transit delay is implemented. `transit_steps` remains descriptive state. |
| Livestock consumer | Even sharing of each source; output equals feed; exit after consecutive zero-feed ticks | This is an operational starvation proxy, not financial bankruptcy or a nutrient-balanced production function. Preserve it pending feed requirements and nutritional data. |
| Market | Quantity-weighted quotes; no demand orders or market clearing | Useful price indicators, not equilibrium prices or realized transaction revenue. Do not add guessed scarcity markups. |

In the original processor rule, 100 tonnes offered at 10 currency/tonne, yield
0.8 and capacity effect 0.5 gave 40 tonnes of output priced as if 50 tonnes of
input were transformed, but reported 100 tonnes as received without explaining
the unused half. Contract 2.0 explicitly reports both quantities. It does not
retroactively claim that every upstream offer was purchased.

## Comparison of economic models

### Fixed-coefficient production and production networks: adopted narrowly

ARIO and firm-network disruption models represent production limits and essential
inputs rather than assuming instantaneous equilibrium [1–3]. Pichler et al. [4]
show that short-run disruption results can depend strongly on the production
function. This supports an explicit bottleneck and cautious model selection,
not treating a particular production function as universally correct.

For one homogeneous input and one output, the implemented technology is
`output = conversion_ratio * input_processed`, with `input_processed` bounded
by offers and throughput. This is a **single-input fixed-yield bottleneck**, not
a full multi-input Leontief/ARIO implementation. Same-good offers are pooled
at a volume-weighted price and consumed proportionally, without price-based
processor supplier choice. Essential energy quantity constraints, multiple
commodities and coproduct accounting need additional host observations.

### Cobb–Douglas and CES production/substitution: deferred

Cobb–Douglas permits substitution among inputs with constant expenditure shares;
CES generalizes the substitution elasticity [5]. Armington demand [8] distinguishes
goods by origin rather than treating all sources as perfect substitutes. These
are plausible alternatives for flexible sourcing and feed substitution.

The current contract contains neither input commodity/nutrient classes nor
estimated substitution elasticities or expenditure budgets. Smooth substitution
could incorrectly imply that essential missing inputs are easily replaced.
Before adoption, supply commodity groups, baseline input quantities, permissible
substitutes, substitution elasticities, capacity and quality constraints through
PDL/sidecar. Compare against the fixed-technology case on held-out disruptions.
No soybean-specific elasticity is inferred from the foundational papers.

### Adaptive inventories and order adjustment: next architectural step

Hallegatte [2] distinguishes essential storable and nonstorable inputs. Inoue
and Todo [3, equations 2–11] explicitly model orders, inventories, production
constraints and rationing. A target-stock adjustment policy can order expected
usage plus a fraction of the gap to desired inventory; inventory days and the
adjustment time are behavior parameters that need calibration. Their paper also
acknowledges limitations in parameter validation.

This mechanism needs persistent stock, opening balances, receipts, dispatches,
losses and one-time allocation/settlement. Merely carrying the current `stock`
attribute forward would count supply twice because downstream actors read
offers rather than debit transactions. Shipment queues also need quantities and
purchase values while goods are in transit. Defer this coordinated engine
change rather than introduce inconsistent local inventory patches.

### Competitive storage and grain-price volatility: deferred

Competitive-storage models relate intertemporal inventories, availability and
prices; Deaton and Laroque [6] and Wright [7] are relevant starting points. Grain
price volatility is a better domain match than importing arbitrary price-response
coefficients from a different sector. However, this model currently lacks
inventory histories, expected future prices, interest/storage costs and an
explicit demand schedule. Competitive storage cannot be honestly implemented as
a multiplier on today's quote. Full paper review and calibration are prerequisites
for reproducing those models; only bibliographic identity was verified here.

### Demand, rationing and price/ordering adjustment: deferred

Equal sharing is a deterministic allocation convention, not demand estimation.
Inoue and Todo [3] demonstrate why rationing assumptions can change propagation;
Armington [8] supplies an alternative origin-differentiated demand framework.
Livestock feed requirements, conversion coefficients, budgets, nutrient content
and substitution limits are missing. Price elasticity without demand allocation
and settlement would leave unaccounted surplus and excess purchases.

Lagged adjustment can be appropriate for orders, sourcing or prices, but lag
coefficients require evidence. Lee et al. [9] analyze information distortion and
the bullwhip effect, motivating scrutiny of ordering dynamics; this is not a
justification to introduce arbitrary smoothing or to claim that cost-plus quotes
are market-clearing prices. Retain the current quote rule while exposing its
assumptions.

## Implemented equations

### Selective operating-cost exposure (all four actors)

Let F be baseline operating expense in currency/step, s[k] the fraction exposed
to input k, and m[k] its host-resolved **price** multiplier. Define

`F_effective = F * (1 - sum(s) + sum(s[k] * m[k]))`.

Shares must be finite, nonnegative and sum to at most one; `capacity` is reserved
for physical effects. The residual share is unexposed. Missing multipliers are
one. An explicit empty mapping leaves all operating cost unexposed. Zero shares
ignore their corresponding effects. Relevant multipliers and F must be finite
nonnegative numbers; booleans and numeric strings are rejected. The helper also
rejects overflow of effective operating cost.

This is expenditure-component accounting under fixed baseline exposures, not an
estimated structural cost function. A fertilizer share of 0.25 with F=100 and
m=2 gives 125, not 200. Shares need not sum to one because labor, rent and other
unmodeled costs remain in the residual. Upstream purchase prices are already
priced goods and are **not** multiplied again by operating-cost shocks.

Producer: `quote = F_effective / produced_quantity * (1 + margin)`.
Trader: `quote = (weighted_purchase_price + F_effective / quantity) * (1 + margin)`.
Transport: `quote = weighted_purchase_price + F_effective / quantity * (1 + margin_transport)`.
The freight margin applies only to freight service, as in contract 1.0.
These are average-cost quotations, not scarcity pricing or profit accounting.

Compatibility defaults: producers use `{"fertilizer": 1.0}`, transport uses
`{"energy": 1.0}`, and traders/processors use `{}`. They preserve the previous
illustrative exposure assumptions and **are not empirical estimates**. A host
must explicitly supply measured cost shares and matching effect bindings to
obtain selective exposure. No gas/fertilizer entity ids are in standalone code.

### Processing throughput and yield

For total offered input Q, active peers n, fixed yield y, physical capacity
effect c and optional per-agent input throughput K:

```
input_received = Q / n
input_processed = min(input_received, K * c)  # explicit K
unused_input = input_received - input_processed
quantity_available = y * input_processed
quote = (weighted_purchase_price / y
         + F_effective / quantity_available) * (1 + margin)
```

When K is `null` (default), use `input_received` as the fallback capacity before
scaling by c. This is a proportional-availability assumption: it preserves the
old loss-shock output but is **not** an absolute throughput ceiling. A supply
gain cannot create material: processing never exceeds the offer. K=0 closes
processing. With explicit K, a half-capacity plant can still process a small
offer in full, instead of reducing every low-volume offer by half. K is per
agent; peers divide offers, not each agent's own capacity.

For Q=100, n=1, K=50, y=.8, input price=10, F=20 and margin=.1: processed=50,
unused=50, output=40, quote=14.3. Before markup, output value is 520: 500 of
processed input and 20 of operating expense. A capacity effect of .5 gives
processed=25, output=20 and quote=14.85. An offer of only 20 is processed fully
under that same 25-unit effective capacity. Yield remains .8 throughout.

`input_received` is an offered equal share, **not settled purchases**;
`unused_input` is that tick's unprocessed offer, **not carried inventory**.
Neither source quantities nor their prices are mutated. A yield below one
leaves a coproduct/waste fraction outside this single-output model; it does not
model soybean oil revenue. Empty inputs or zero peers clear all flow fields;
zero output has zero quote. This does not imply fixed expenses disappear in
a financial ledger, which is not implemented.

Yield must be finite and strictly positive, throughput capacity null or finite
nonnegative, capacity effects/source prices/quantities finite nonnegative, and
peers a nonnegative nonboolean integer. Semantic checks apply without optional
jsonschema, including externally synchronized economic state. Generic fallback
schema checking remains intentionally limited for other legacy fields.

## Contract 2.0 migration

- Every OFFIS setup output includes `input_cost_shares`; hosts synchronizing
  mutable state must preserve it and treat returned mappings as snapshots.
- Process setup/state add `throughput_capacity`, `input_processed`,
  `unused_input`. Every active process action includes both new diagnostics.
- `input_received` retains its offered-share meaning; consumers of that field
  should use `input_processed` for material actually transformed.
- Zero conversion ratio now fails validation. Capacity gains are bounded by
  available input. Use null capacity only when the fallback assumption is intended.
- Inactive actors retain no-op actions; existing unknown-role handling remains.
- Standalone contracts stay plain dictionaries with JSON-serializable schemas;
  the abstract `AgentSpec` default is unchanged. Hosts must negotiate the OFFIS
  version rather than assume a 1.0 output schema accepts new fields.
- simenv must use the updated agents first. Its configured main-branch dependency
  is unchanged; local editable installation is the development override.

## Validation and calibration protocol

1. Define observables before fitting: production, input/output yields,
   delivered quantities, operating expenses and cost-plus quotes are different
   from inventory, realized transactions and market prices.
2. Collect baseline and disrupted plant throughput, utilization, yield, cost
   shares and input prices in consistent daily tonnes/currency units. Store
   source, date, uncertainty and aggregation scale with scenario parameters.
3. Separate calibration and held-out time windows/events. Fit baseline yield,
   capacity and exposures on calibration data; retain a no-shock comparison.
4. Test structural identities and comparative statics separately from fit:
   processed<=offer/capacity; output=yield*processed; exposed/unexposed costs
   reconcile; physical shocks do not become price shocks.
5. Compare held-out volume and price errors to contract 1.0 and simple reference
   forecasts. Do not improve one variable by silently degrading another.
6. Perform sensitivity analysis over uncertain capacities, yields, exposures,
   seeds and timing conventions; report ranges rather than one illustrative run.
7. When extending inventories/demand, compare alternative production and rationing
   assumptions. Windrum et al. [10] emphasize identification, empirical validation
   and sensitivity; more parameters alone are not validation.

The regression suite covers selective costs in all four actors, analytical
throughput examples, unequal-price input pooling, zero/empty boundaries,
nonfinite/type rejection, fallback validation and mutable-state isolation.
simenv tests cover renamed entities, sidecar configuration, adapter parity,
recording, old-view upgrades and historical/new strict-JSON exports.

## Sources and verification scope

The bibliography was checked through DOI metadata, article abstracts and accessible
full texts. **Metadata-only** means identity was verified, not the full paper's
equations, empirical results or suitability of its coefficients.

1. Hallegatte, S. (2008). *An Adaptive Regional Input-Output Model and its
   Application to the Assessment of the Economic Cost of Katrina.* Risk Analysis
   28(3), 779–799. [DOI](https://doi.org/10.1111/j.1539-6924.2008.01046.x).
   Metadata verified; interpretation is cross-checked through [2,3].
2. Hallegatte, S. (2014). *Modeling the Role of Inventories and Heterogeneity in
   the Assessment of the Economic Costs of Natural Disasters.* Risk Analysis
   34(1), 152–167. [DOI](https://doi.org/10.1111/risa.12090).
   Crossref abstract and metadata inspected; online publication 2013, volume 2014.
3. Inoue, H. & Todo, Y. (2019). *Propagation of negative shocks across nation-wide
   firm networks.* PLOS ONE 14(3), e0213648.
   [Full text](https://doi.org/10.1371/journal.pone.0213648).
   Full text inspected, particularly theoretical model, rationing and limitations.
4. Pichler, A., Pangallo, M., del Rio-Chanona, R. M., Lafond, F. & Farmer, J. D.
   (2020). *Production networks and epidemic spreading: How to restart the UK
   economy?* [arXiv:2005.10585](https://arxiv.org/abs/2005.10585).
   Abstract inspected; citation is to the preprint, not a verified journal version.
5. Arrow, K. J., Chenery, H. B., Minhas, B. S. & Solow, R. M. (1961).
   *Capital-Labor Substitution and Economic Efficiency.* Review of Economics and
   Statistics 43(3), 225–250. [DOI](https://doi.org/10.2307/1927286).
   Metadata only; foundational CES reference, not soybean elasticity evidence.
6. Deaton, A. & Laroque, G. (1992). *On the Behaviour of Commodity Prices.* Review
   of Economic Studies 59(1), 1–23. [DOI](https://doi.org/10.2307/2297923).
   Metadata only; candidate storage literature, not a reproduced model.
7. Wright, B. D. (2011). *The Economics of Grain Price Volatility.* Applied Economic
   Perspectives and Policy 33(1), 32–58.
   [DOI](https://doi.org/10.1093/aepp/ppq033). Metadata only.
8. Armington, P. S. (1969). *A Theory of Demand for Products Distinguished by Place
   of Production.* IMF Staff Papers 16(1), 159–178.
   [DOI](https://doi.org/10.2307/3866403). Metadata only; candidate demand model.
9. Lee, H. L., Padmanabhan, V. & Whang, S. (1997). *Information Distortion in a
   Supply Chain: The Bullwhip Effect.* Management Science 43(4), 546–558.
   [DOI](https://doi.org/10.1287/mnsc.43.4.546). Metadata only.
10. Windrum, P., Fagiolo, G. & Moneta, A. (2007). *Empirical Validation of
    Agent-Based Models: Alternatives and Prospects.* JASSS 10(2), 8.
    [Full text](https://www.jasss.org/10/2/8.html).
    Full text inspected, especially sections 2–4 on calibration and identification.
