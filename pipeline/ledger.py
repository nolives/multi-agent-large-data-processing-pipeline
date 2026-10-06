"""Rates, a shared spend ledger and a shared request-rate limiter. All are safe to use from several workers."""

import csv
import threading
import time
from pathlib import Path


def load_rates(path):
    """rates.csv -> {(provider, model, billing_item): price per single unit}."""
    rates = {}
    with Path(path).open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rates[(row["provider"], row["model"], row["billing_item"])] = float(row["price_per_million_units"]) / 1_000_000
    return rates


def call_cost(rates, provider, model, input_tokens, output_tokens, cache_read_tokens=0, cache_write_tokens=0):
    # item_cost = billed_units x price_per_unit, summed over mutually exclusive billing items.
    items = {"input_tokens": input_tokens, "output_tokens": output_tokens,
             "cache_read_tokens": cache_read_tokens, "cache_write_tokens": cache_write_tokens}
    return sum(units * rates[(provider, model, item)] for item, units in items.items() if units)


class SpendLedger:
    """Reserve worst-case cost before a call is sent; settle it with the actual cost afterwards."""

    def __init__(self, cap_usd):
        self.cap, self.spent, self.reserved = cap_usd, 0.0, 0.0
        self.lock = threading.Lock()

    def reserve(self, amount):
        with self.lock:
            if self.spent + self.reserved + amount > self.cap:
                return False
            self.reserved += amount
            return True

    def settle(self, reserved, actual):
        with self.lock:
            self.reserved -= reserved
            self.spent += actual


class RateLimiter:
    """Space request starts evenly across all workers, and honour a shared pause after a rate-limit response."""

    def __init__(self, max_per_second, sleep=time.sleep, clock=time.monotonic):
        self.interval, self.sleep, self.clock = 1.0 / max_per_second, sleep, clock
        self.next_start = 0.0
        self.lock = threading.Lock()

    def wait(self):
        with self.lock:
            now = self.clock()
            start = max(now, self.next_start)
            self.next_start = start + self.interval
        if start > now:
            self.sleep(start - now)

    def pause(self, seconds):
        with self.lock:
            self.next_start = max(self.next_start, self.clock() + seconds)
