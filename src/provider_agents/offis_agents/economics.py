"""Small economic policies with explicit units and schema-independent domains."""

import math
from numbers import Real


def nonnegative(value, name: str) -> float:
    """Reject coercions, booleans and non-finite economic measurements."""
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite non-negative number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite non-negative number")
    return value


def validate_cost_shares(shares: dict[str, float]) -> None:
    if not isinstance(shares, dict):
        raise ValueError("input_cost_shares must be a mapping")
    for slot, share in shares.items():
        if not isinstance(slot, str) or not slot or slot == "capacity":
            raise ValueError("cost-share slots must be nonempty strings other than capacity")
        nonnegative(share, f"input_cost_shares.{slot}")
    if math.fsum(shares.values()) > 1:
        raise ValueError("input_cost_shares must sum to at most one")


def operating_cost(base: float, shares: dict[str, float], effects: dict[str, float]) -> float:
    """Reprice exposed operating costs, leaving upstream purchase prices alone."""
    nonnegative(base, "fixed_costs")
    validate_cost_shares(shares)
    validate_cost_effects(shares, effects)
    exposed = []
    for slot, share in shares.items():
        if share:
            multiplier = nonnegative(effects.get(slot, 1.), f"effects.{slot}")
            exposed.append(share * multiplier)
    result = base * (1. - math.fsum(shares.values()) + math.fsum(exposed))
    return nonnegative(result, "effective operating cost")


def validate_cost_effects(shares, effects):
    """Exposed price domains also apply during temporary closures/empty flows."""
    if not isinstance(effects, dict):
        raise ValueError("effects must be a mapping")
    for slot, share in shares.items():
        if share:
            nonnegative(effects.get(slot, 1.), f"effects.{slot}")
