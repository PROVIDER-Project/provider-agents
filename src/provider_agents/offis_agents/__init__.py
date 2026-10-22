"""Standalone agent implementations owned by OFFIS."""

from .farmer_provider_agent import ROLE_CONSUMER, ROLE_PRODUCER, FarmerProviderAgent
from .process_provider_agent import ROLE_FEED_MANUFACTURER, ROLE_PROCESSOR, ProcessProviderAgent
from .trader_provider_agent import ROLE_FEED_TRADER, ROLE_WHOLESALER, TraderProviderAgent

__all__ = [
    "FarmerProviderAgent", "ProcessProviderAgent", "TraderProviderAgent",
    "ROLE_CONSUMER", "ROLE_PRODUCER", "ROLE_PROCESSOR", "ROLE_FEED_MANUFACTURER",
    "ROLE_FEED_TRADER", "ROLE_WHOLESALER",
]
