from dataclasses import dataclass
from enum import StrEnum
from time import monotonic

from mcp_one.config import CircuitBreakerPolicy
from mcp_one.domain.errors import ErrorCode, GatewayError


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass(frozen=True)
class Permit:
    epoch: int
    probe: bool


class CircuitBreaker:
    """Event-loop confined. Admission/settlement never yield; one half-open probe."""

    def __init__(self, policy: CircuitBreakerPolicy):
        self.policy = policy
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.opened_at = 0.0
        self.epoch = 0

    def acquire(self, now: float | None = None) -> Permit:
        now = monotonic() if now is None else now
        if not self.policy.enabled:
            return Permit(self.epoch, False)
        if self.state == CircuitState.OPEN and now - self.opened_at >= self.policy.reset_seconds:
            self.state = CircuitState.HALF_OPEN
            return Permit(self.epoch, True)
        if self.state != CircuitState.CLOSED:
            raise GatewayError(ErrorCode.CIRCUIT_OPEN, infrastructure=True)
        return Permit(self.epoch, False)

    def settle(self, permit: Permit, *, failed: bool, now: float | None = None) -> bool:
        if not self.policy.enabled or permit.epoch != self.epoch:
            return False
        if failed:
            self.failures += 1
            if permit.probe or self.failures >= self.policy.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = monotonic() if now is None else now
                self.epoch += 1
                return True
        elif permit.probe or self.state == CircuitState.CLOSED:
            self.state = CircuitState.CLOSED
            self.failures = 0
        return False

    def abandon(self, permit: Permit) -> None:
        # Cancellation is not a downstream failure; release the probe without closing the circuit.
        if permit.probe and permit.epoch == self.epoch:
            self.state = CircuitState.OPEN

    @property
    def can_attempt(self) -> bool:
        return self.state == CircuitState.CLOSED or (
            self.state == CircuitState.OPEN
            and monotonic() - self.opened_at >= self.policy.reset_seconds
        )
