"""Fallback behaviour of GeminiClient: 429/5xx/timeouts fall through to the
next candidate model, within the timeout invariant in CLAUDE.md.

stdlib unittest + httpx.MockTransport only — no test dependencies.
Run: python -m unittest discover -s tests
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import httpx  # noqa: E402

import gemini  # noqa: E402
import reviewer  # noqa: E402

OK_BODY = {"candidates": [{"content": {"parts": [{"text": "LGTM"}]}}]}


def _model_of(request: httpx.Request) -> str:
    return request.url.path.rsplit("/", 1)[-1].split(":", 1)[0]


def _status(code: int, status: str, message: str = "") -> httpx.Response:
    return httpx.Response(code, json={"error": {"code": code, "status": status, "message": message}})


def _daily_429() -> httpx.Response:
    return httpx.Response(
        429,
        json={
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [{"quotaId": "GenerateRequestsPerDayPerProjectPerModel"}],
                    }
                ],
            }
        },
    )


class _Router:
    """MockTransport handler: per-model scripted behaviour, records calls."""

    def __init__(self, behaviours: dict) -> None:
        self.behaviours = behaviours
        self.calls: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        model = _model_of(request)
        self.calls.append(model)
        return await self.behaviours[model](request)


def _always(response_factory):
    async def handler(request):
        return response_factory()
    return handler


def _raise(exc_type):
    async def handler(request):
        raise exc_type("boom", request=request)
    return handler


def _hang(request):
    async def handler(request):
        await asyncio.sleep(3600)
    return handler(request)


def _client(router: _Router, models: list[str]) -> gemini.GeminiClient:
    return gemini.GeminiClient(
        api_key="test-key",
        model=models[0],
        fallback_models=models[1:],
        transport=httpx.MockTransport(router),
    )


async def _review(client: gemini.GeminiClient) -> str:
    return await client.generate_review("t", "b", "- `f.py`", "diff --git a/f.py b/f.py")


# Budgets small enough that the backoff (2s, 4s, ...) never fits, so 5xx gives
# up on a model after one attempt and the tests stay fast.
FAST = dict(RETRY_BUDGET_SECONDS=1.0, REQUEST_TIMEOUT_SECONDS=1.0, MIN_REQUEST_SECONDS=0.05)


@mock.patch.multiple(gemini, **FAST)
class FallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_503_falls_through_to_next_model(self):
        router = _Router({
            "primary": _always(lambda: _status(503, "UNAVAILABLE", "high demand")),
            "lite": _always(lambda: httpx.Response(200, json=OK_BODY)),
        })
        self.assertEqual(await _review(_client(router, ["primary", "lite"])), "LGTM")
        self.assertEqual(router.calls, ["primary", "lite"])

    async def test_500_falls_through_to_next_model(self):
        router = _Router({
            "primary": _always(lambda: _status(500, "INTERNAL")),
            "lite": _always(lambda: httpx.Response(200, json=OK_BODY)),
        })
        self.assertEqual(await _review(_client(router, ["primary", "lite"])), "LGTM")
        self.assertEqual(router.calls, ["primary", "lite"])

    async def test_read_timeout_falls_through_without_retrying_same_model(self):
        router = _Router({
            "primary": _raise(httpx.ReadTimeout),
            "lite": _always(lambda: httpx.Response(200, json=OK_BODY)),
        })
        self.assertEqual(await _review(_client(router, ["primary", "lite"])), "LGTM")
        self.assertEqual(router.calls, ["primary", "lite"])

    async def test_connect_timeout_falls_through(self):
        router = _Router({
            "primary": _raise(httpx.ConnectTimeout),
            "lite": _always(lambda: httpx.Response(200, json=OK_BODY)),
        })
        self.assertEqual(await _review(_client(router, ["primary", "lite"])), "LGTM")

    async def test_hung_request_is_capped_and_falls_through(self):
        # httpx's timeout is per read; a request that never completes must
        # still be cut off at REQUEST_TIMEOUT_SECONDS by our own cap.
        router = _Router({
            "primary": _hang,
            "lite": _always(lambda: httpx.Response(200, json=OK_BODY)),
        })
        with mock.patch.object(gemini, "REQUEST_TIMEOUT_SECONDS", 0.2):
            self.assertEqual(await _review(_client(router, ["primary", "lite"])), "LGTM")
        self.assertEqual(router.calls, ["primary", "lite"])

    async def test_400_does_not_fall_through(self):
        router = _Router({
            "primary": _always(lambda: _status(400, "INVALID_ARGUMENT")),
            "lite": _always(lambda: httpx.Response(200, json=OK_BODY)),
        })
        with self.assertRaises(httpx.HTTPStatusError):
            await _review(_client(router, ["primary", "lite"]))
        self.assertEqual(router.calls, ["primary"])

    async def test_503_retries_same_model_when_budget_allows(self):
        responses = iter([_status(503, "UNAVAILABLE"), httpx.Response(200, json=OK_BODY)])
        router = _Router({"primary": _always(lambda: next(responses))})
        with mock.patch.object(gemini.asyncio, "sleep", new=mock.AsyncMock()) as sleep, \
                mock.patch.object(gemini, "RETRY_BUDGET_SECONDS", 45.0):
            self.assertEqual(await _review(_client(router, ["primary", "lite"])), "LGTM")
        self.assertEqual(router.calls, ["primary", "primary"])
        sleep.assert_awaited_once_with(2)


class DeadlineTests(unittest.IsolatedAsyncioTestCase):
    async def test_hard_deadline_bounds_total_time_and_skips_candidates(self):
        # Every model hangs. Budget: sleeps 0.1s + request 0.2s = 0.3s total.
        # m1 is cut at 0.2s, m2 gets the remaining ~0.1s, m3 must never start.
        router = _Router({m: _hang for m in ("m1", "m2", "m3")})
        with mock.patch.multiple(
            gemini, RETRY_BUDGET_SECONDS=0.1, REQUEST_TIMEOUT_SECONDS=0.2, MIN_REQUEST_SECONDS=0.05
        ):
            start = time.monotonic()
            with self.assertRaises(gemini.GeminiUnavailable) as ctx:
                await _review(_client(router, ["m1", "m2", "m3"]))
            elapsed = time.monotonic() - start
        self.assertEqual(router.calls, ["m1", "m2"])
        self.assertLess(elapsed, 0.3 + 0.15)
        self.assertEqual(ctx.exception.skipped, ["m3"])
        self.assertEqual(
            ctx.exception.status_description, "Gemini timed out on m1, m2; no time left for m3"
        )

    async def test_default_budget_fits_lambda_timeout(self):
        # The invariant itself: worst case Gemini wall-clock < Lambda timeout (120s).
        self.assertLess(gemini.RETRY_BUDGET_SECONDS + gemini.REQUEST_TIMEOUT_SECONDS, 120)


@mock.patch.multiple(gemini, **FAST)
class AllFailStatusTests(unittest.IsolatedAsyncioTestCase):
    async def _all_fail(self, behaviour, models=("gemini-3.5-flash", "gemini-3.5-flash-lite")):
        router = _Router({m: behaviour for m in models})
        with self.assertRaises(gemini.GeminiUnavailable) as ctx:
            await _review(_client(router, list(models)))
        self.assertEqual(router.calls, list(models))
        return ctx.exception

    async def test_all_503(self):
        exc = await self._all_fail(_always(lambda: _status(503, "UNAVAILABLE")))
        self.assertNotIsInstance(exc, gemini.GeminiQuotaExhausted)
        self.assertEqual(
            exc.status_description,
            "Gemini unavailable (503) on gemini-3.5-flash, gemini-3.5-flash-lite",
        )

    async def test_all_timeout(self):
        exc = await self._all_fail(_raise(httpx.ReadTimeout))
        self.assertEqual(
            exc.status_description, "Gemini timed out on gemini-3.5-flash, gemini-3.5-flash-lite"
        )

    async def test_all_429_keeps_quota_wording_and_type(self):
        exc = await self._all_fail(_always(_daily_429))
        self.assertIsInstance(exc, gemini.GeminiQuotaExhausted)
        self.assertEqual(
            exc.status_description,
            "Gemini quota exhausted (gemini-3.5-flash, gemini-3.5-flash-lite)",
        )

    async def test_mixed_failures_name_each_model(self):
        router = _Router({
            "a": _always(lambda: _status(503, "UNAVAILABLE")),
            "b": _raise(httpx.ReadTimeout),
            "c": _always(_daily_429),
        })
        with self.assertRaises(gemini.GeminiUnavailable) as ctx:
            await _review(_client(router, ["a", "b", "c"]))
        self.assertEqual(ctx.exception.status_description, "Gemini failed: a 503, b timeout, c quota")

    async def test_description_fits_github_limit(self):
        models = [f"gemini-very-long-model-name-{i}" for i in range(8)]
        exc = await self._all_fail(_always(lambda: _status(503, "UNAVAILABLE")), models)
        self.assertLessEqual(len(exc.status_description), 140)
        self.assertTrue(exc.status_description.startswith("Gemini unavailable (503) on "))


class ReviewerStatusTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_sets_descriptive_error_status_and_does_not_raise(self):
        failure = gemini.GeminiUnavailable(
            [gemini._ModelUnavailable("x", "unavailable", 503), gemini._ModelUnavailable("y", "unavailable", 503)]
        )
        payload = {"repository": {"full_name": "o/r"}, "pull_request": {"head": {"sha": "abc"}}}
        with mock.patch.object(reviewer, "_run_pr_review_pipeline", side_effect=failure), \
                mock.patch.object(reviewer, "_report_status", new=mock.AsyncMock()) as report:
            result = await reviewer.run_pr_review_pipeline(payload)
        self.assertEqual(result, {"success": False, "reason": "gemini_unavailable"})
        report.assert_awaited_once_with("o/r", "abc", "error", "Gemini unavailable (503) on x, y")


if __name__ == "__main__":
    unittest.main()
