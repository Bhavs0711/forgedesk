import random


def delay(attempt: int, base: float, cap: float, jitter: bool = True) -> float:
    """Exponential backoff: base * 2^(attempt-1), capped, with up to 25% jitter."""
    d = min(cap, base * (2 ** max(0, attempt - 1)))
    return d * (1 + random.uniform(-0.25, 0.25)) if jitter else d
