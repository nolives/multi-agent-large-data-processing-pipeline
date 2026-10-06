"""One structured-output call to Claude with bounded retries, a spend reservation and a full attempt log.

Used by the verify, group and memo roles. Each role passes its own instructions, input and JSON schema.
The SDK's built-in retries are turned off so that every attempt, including failures, is recorded.
"""

import json
import random
import time
import uuid

import anthropic

from .ledger import call_cost
from .store import new_call

PROVIDER = "anthropic"
MAX_BACKOFF_SECONDS = 30


class ClaudeCaller:
    def __init__(self, *, api_key, rates, ledger, max_attempts=4, timeout=180.0, http_client=None, sleep=time.sleep):
        self.client = anthropic.Anthropic(api_key=api_key, max_retries=0, timeout=timeout, http_client=http_client)
        self.rates, self.ledger, self.max_attempts, self.sleep = rates, ledger, max_attempts, sleep

    def call(self, *, role, model, label_config, system, user, schema, max_tokens, review_ids=(), effort=None):
        """Returns (kind, data, calls). kind is ok, invalid, refusal, transient, fatal or spend_cap."""
        calls = []
        # Worst case for the reservation: a generous input estimate plus the full output allowance.
        reservation = call_cost(self.rates, PROVIDER, model, len((system + user).encode("utf-8")) // 2, max_tokens)
        output_config = {"format": {"type": "json_schema", "schema": schema}}
        if effort:
            output_config["effort"] = effort
        for attempt in range(1, self.max_attempts + 1):
            if not self.ledger.reserve(reservation):
                return "spend_cap", None, calls
            call = new_call(role, PROVIDER, model, label_config, review_ids, attempt, f"claude-{uuid.uuid4().hex}")
            calls.append(call)
            clock = time.monotonic()
            retry_after = None
            try:
                message = self.client.messages.create(model=model, max_tokens=max_tokens, system=system,
                                                      messages=[{"role": "user", "content": user}], output_config=output_config)
            except anthropic.APITimeoutError:
                # The request may have been processed and billed; charge the reservation and flag it.
                call.update(error="timeout", usage_unknown=True, cost_usd=reservation)
                self.ledger.settle(reservation, reservation)
            except anthropic.APIConnectionError as e:
                call.update(error=f"connection: {type(e).__name__}")
                self.ledger.settle(reservation, 0.0)
            except anthropic.APIStatusError as e:
                call.update(error=f"http_{e.status_code}", status_code=e.status_code,
                            provider_request_id=e.response.headers.get("request-id"))
                self.ledger.settle(reservation, 0.0)
                if not (e.status_code in (408, 409, 429) or e.status_code >= 500):
                    call["duration_ms"] = round((time.monotonic() - clock) * 1000)
                    return "fatal", str(e)[:300], calls
                try:
                    retry_after = float(e.response.headers.get("retry-after", ""))
                except ValueError:
                    pass
            else:
                usage = message.usage
                call.update(status_code=200, provider_request_id=message._request_id, duration_ms=round((time.monotonic() - clock) * 1000),
                            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
                            cache_read_tokens=usage.cache_read_input_tokens or 0,
                            cache_write_tokens=usage.cache_creation_input_tokens or 0)
                call["cost_usd"] = call_cost(self.rates, PROVIDER, model, call["input_tokens"], call["output_tokens"],
                                             call["cache_read_tokens"], call["cache_write_tokens"])
                self.ledger.settle(reservation, call["cost_usd"])
                # An alias such as claude-haiku-4-5 is answered by a dated snapshot of the same model; log the exact ID served.
                if message.model != model and not message.model.startswith(model + "-"):
                    call["error"] = f"invalid_output: answered by {message.model!r}, not the configured model"
                    return "invalid", None, calls
                call["model"] = message.model
                if message.stop_reason == "refusal":
                    call["error"] = "refusal"
                    return "refusal", None, calls
                if message.stop_reason != "end_turn":
                    call["error"] = f"invalid_output: stopped with {message.stop_reason}"
                    return "invalid", None, calls
                try:
                    data = json.loads(next(block.text for block in message.content if block.type == "text"))
                except (StopIteration, ValueError):
                    call["error"] = "invalid_output: no JSON text block"
                    return "invalid", None, calls
                call["outcome"] = "succeeded"
                return "ok", data, calls
            call["duration_ms"] = round((time.monotonic() - clock) * 1000)
            if attempt < self.max_attempts:
                delay = max(min(MAX_BACKOFF_SECONDS, 2 ** (attempt - 1)) * random.uniform(0.5, 1.5), retry_after or 0)
                self.sleep(delay)
        return "transient", None, calls
