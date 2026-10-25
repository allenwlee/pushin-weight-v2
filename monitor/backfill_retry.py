"""Bounded recovery for staging search GETs; never used by scheduled harvesting."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

from core.measurement_taxonomy import require

POLICY = "staging-get-retry/v1"
PAGE_FAILURE_LIMIT = 5
COOLDOWNS = (60, 300, 900)


def transient(error, status):
    # Missing/malformed replies and unknown sends are not transport failures.
    return status in {429, 500, 502, 503, 504} or (
        status is None and error in {"Timeout", "ConnectionError"}
    )


@dataclass
class RetryControl:
    phase: str = "closed"
    failures: list[float] = field(default_factory=list)
    cooldowns: int = 0
    until: float = 0
    successes: int = 0

    @classmethod
    def restore(cls, saved):
        if saved is None:
            return cls()
        require(set(saved) == {"policy", "phase", "failures", "cooldowns", "until", "successes"}
                and saved["policy"] == POLICY, "invalid staging retry state")
        value = cls(**{k: v for k, v in saved.items() if k != "policy"})
        require(value.phase in {"closed", "open", "probe", "ramp"}
                and type(value.cooldowns) is int and 0 <= value.cooldowns <= len(COOLDOWNS)
                and type(value.successes) is int and 0 <= value.successes <= 4
                and isinstance(value.failures, list) and len(value.failures) <= 3,
                "invalid staging retry state")
        import math
        require(all(type(n) in {int, float} and math.isfinite(n) and n >= 0
                    for n in [value.until, *value.failures]), "invalid staging retry time")
        return value

    def snapshot(self):
        return {"policy": POLICY, **asdict(self)}

    def limit(self, configured, now):
        if self.phase == "open":
            if now < self.until:
                return 0
            self.phase = "probe"
        return min(configured, {"probe": 1, "ramp": 4}.get(self.phase, configured))

    def failed(self, now, *, retry_after=0, rate_limited=False):
        # Late failures from the wave being drained do not advance the cooldown.
        if self.phase == "open":
            self.until = max(self.until, now + retry_after)
            return
        self.failures = [t for t in self.failures if now - t <= 60][-2:] + [now]
        if self.phase != "closed" or len(self.failures) >= 3 or rate_limited:
            delay = COOLDOWNS[min(self.cooldowns, len(COOLDOWNS) - 1)]
            self.cooldowns = min(self.cooldowns + 1, len(COOLDOWNS))
            self.phase, self.until, self.successes = "open", now + max(delay, retry_after), 0

    def succeeded(self):
        if self.phase == "probe":
            self.phase, self.successes = "ramp", 0
        elif self.phase == "ramp":
            self.successes += 1
            if self.successes >= 4:
                self.phase, self.cooldowns, self.successes = "closed", 0, 0
                self.failures, self.until = [], 0
