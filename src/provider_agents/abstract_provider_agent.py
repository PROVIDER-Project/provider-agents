"""Abstract base contract for simulation agents.

This module introduces a formal ABC for agent implementations.
"""

from abc import ABC, abstractmethod
from typing import Any


class AbstractPROVIDERAgent(ABC):
    """Abstract interface and shared helpers for all supply chain agents."""

    @abstractmethod
    def setup(self, data_in: dict[str, Any]) -> dict[str, Any]:
        """Initialise shared and role-specific state for the agent. 
        Take any parameters as input from `data_in` and return any initial state via `data_out`."""
        raise NotImplementedError

    @abstractmethod
    def step(self, data_in: dict[str, Any]) -> dict[str, Any]:
        """Advance the agent by one simulation step. 
        Take all required data as `data_in` and return any agent actions via `data_out`."""
        raise NotImplementedError
