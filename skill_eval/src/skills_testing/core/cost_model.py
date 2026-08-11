"""
Cost / economic model for the benchmark.

Loads the ``model_pricing`` block from ``pricing.yaml`` (split out of
``config.yaml`` -- see that file's header comment) and computes a
per-query USD cost from token counts (for hosted API models) or from
**calendar-hour amortization** of the underlying machine (for self-hosted
SLMs).  Hardware you own depreciates 24/7 whether you use it or not, so
the per-query cost is::

    hourly_rate    = capex_usd / (useful_life_years * 8760)
                   + avg_power_watts / 1000 * electricity_usd_per_kwh
    query_cost_usd = elapsed_s / 3600 * hourly_rate

This keeps per-query cost stable regardless of utilization, and lets a
single ``machines`` block model multiple boxes (Strix Halo, A100 spot,
RTX 4090 workstation, ...) with honest accounting.

Also computes the cost-adjusted composite score and the quality-per-dollar
metric used by the dashboard.

This module is intentionally dependency-free beyond the standard library
plus PyYAML so it can be re-used by the report generator and the
backfill script without dragging in heavy ML imports.
"""

from __future__ import annotations

import fnmatch
import math
from pathlib import Path
from typing import Any

import yaml

# Hours in a calendar year (365 * 24).  Used for capex amortization.
HOURS_PER_YEAR = 365 * 24  # 8760

# Cache the parsed config once per process so callers can invoke
# ``compute_cost`` cheaply in a tight loop (backfill walks every row).
_CACHED_CONFIG: dict | None = None
# Memoize per-machine hourly rates: machine name → (rate_usd_per_hr, breakdown_dict)
_MACHINE_RATE_CACHE: dict[str, tuple[float, dict]] = {}


def load_config(
    config_path: Path | str | None = None,
    pricing_path: Path | str | None = None,
) -> dict:
    """Load and cache the test-suite config, merged with ``pricing.yaml``.

    ``model_pricing`` lives in its own file (``pricing.yaml``, next to
    ``config.yaml``) since it's externally-sourced vendor data on a
    different maintenance cadence than harness behavior config -- see
    ``config.yaml``'s header comment. It's merged back into the returned
    dict under the same ``model_pricing`` key so every caller in this
    module (``_pricing_block`` and everything built on it) is unaffected
    by the split. A missing pricing file degrades to "no pricing data"
    (``model_pricing: {}``) rather than an error, matching how a missing
    ``config.yaml`` behaves below.
    """
    from skills_testing.core.paths import DEFAULT_CONFIG, DEFAULT_PRICING_CONFIG

    global _CACHED_CONFIG
    config_is_default = config_path is None or Path(config_path).resolve() == DEFAULT_CONFIG.resolve()
    pricing_is_default = pricing_path is None or Path(pricing_path).resolve() == DEFAULT_PRICING_CONFIG.resolve()
    is_default = config_is_default and pricing_is_default
    if is_default and _CACHED_CONFIG is not None:
        return _CACHED_CONFIG
    with open(config_path or DEFAULT_CONFIG) as f:
        cfg = yaml.safe_load(f) or {}
    pricing_file = Path(pricing_path or DEFAULT_PRICING_CONFIG)
    if pricing_file.exists():
        with open(pricing_file) as f:
            pricing_cfg = yaml.safe_load(f) or {}
        cfg["model_pricing"] = pricing_cfg.get("model_pricing", {})
    else:
        cfg.setdefault("model_pricing", {})
    if is_default:
        _CACHED_CONFIG = cfg
        # Bust the per-machine cache whenever we reload the canonical config.
        _MACHINE_RATE_CACHE.clear()
    return cfg


def _pricing_block(config: dict | None = None) -> dict:
    cfg = config or load_config()
    return cfg.get("model_pricing", {}) or {}


def _resolve_pricing(model: str, pricing: dict) -> dict | None:
    """
    Resolve the per-model pricing entry.  Supports glob patterns
    (e.g. ``lemonade/*``) so a single rule covers all Lemonade models.

    Tries, in order: the full id, then the provider-stripped bare name
    (drop a ``lemonade/``-style prefix or a ``user.`` prefix) -- each first
    literally, then case-insensitively, then against glob keys. A
    gateway-qualified id like ``amd-anthropic/Claude-Sonnet-4.5`` needs all
    of this: it differs from the ``claude-sonnet-4.5`` row only by prefix and
    case, and a differently-cased id like ``amd-gateway/gpt-5.6-sol-high``
    needs the ``gpt-5.6-sol*`` glob applied to the bare name, not the
    prefixed one.
    """
    models = pricing.get("models", {}) or {}
    bare = model.split("/", 1)[1] if "/" in model else model
    bare = bare.split(".", 1)[1] if bare.startswith("user.") else bare
    candidates = (model, bare) if bare != model else (model,)

    for candidate in candidates:
        if candidate in models:
            return models[candidate]

    for candidate in candidates:
        lower = candidate.lower()
        for key, value in models.items():
            if "*" not in key and key.lower() == lower:
                return value

    for candidate in candidates:
        for key, value in models.items():
            if "*" in key and fnmatch.fnmatch(candidate, key):
                return value

    for candidate in candidates:
        lower = candidate.lower()
        for key, value in models.items():
            if "*" in key and fnmatch.fnmatch(lower, key.lower()):
                return value

    return None


def _machine_hourly_rate(
    name: str, machine_cfg: dict, *,
    measured_avg_watts: float | None = None,
) -> tuple[float, dict]:
    """
    Compute the calendar-hour cost of owning + powering a single machine.

    Returns ``(rate_usd_per_hour, breakdown)`` where ``breakdown`` is a small
    dict useful for tooltips / debugging.

    Power input precedence:
      1. ``measured_avg_watts`` — actual sampled draw during the test.  When
         provided, this overrides config and *bypasses the per-machine cache*
         (since each test row may have its own measurement).
      2. ``machine_cfg["avg_power_watts"]`` — static fallback from config.

    Special case: a machine entry with ``override_hourly_usd`` (e.g. cloud
    spot) skips the capex/electricity math and uses the literal rate.
    """
    if measured_avg_watts is None:
        cached = _MACHINE_RATE_CACHE.get(name)
        if cached is not None:
            return cached

    if "override_hourly_usd" in machine_cfg:
        rate = float(machine_cfg["override_hourly_usd"])
        breakdown = {"override_hourly_usd": rate}
        if measured_avg_watts is None:
            _MACHINE_RATE_CACHE[name] = (rate, breakdown)
        return rate, breakdown

    capex = float(machine_cfg.get("capex_usd", 0) or 0)
    life_years = float(machine_cfg.get("useful_life_years", 0) or 0)
    static_w = float(machine_cfg.get("avg_power_watts", 0) or 0)
    avg_watts = float(measured_avg_watts) if measured_avg_watts is not None else static_w
    elec_rate = float(machine_cfg.get("electricity_usd_per_kwh", 0) or 0)

    capex_per_hour = capex / (life_years * HOURS_PER_YEAR) if life_years > 0 else 0.0
    elec_per_hour = (avg_watts / 1000.0) * elec_rate
    rate = capex_per_hour + elec_per_hour
    breakdown = {
        "capex_usd": capex,
        "useful_life_years": life_years,
        "capex_per_hour": capex_per_hour,
        "avg_power_watts": avg_watts,
        "static_avg_power_watts": static_w,
        "power_source": "measured" if measured_avg_watts is not None else "config",
        "electricity_usd_per_kwh": elec_rate,
        "electricity_per_hour": elec_per_hour,
        "hourly_rate": rate,
    }
    if measured_avg_watts is None:
        _MACHINE_RATE_CACHE[name] = (rate, breakdown)
    return rate, breakdown


def _resolve_self_hosted_hourly(
    rule: dict, pricing: dict, *,
    power_metrics: dict | None = None,
) -> tuple[float, str]:
    """
    Decide how to bill an hour of compute for a self-hosted model.

    Preference order:
      1. The machine referenced by the model rule (``machine: <name>``) —
         honest calendar-hour amortization, augmented with measured average
         active power if ``power_metrics["avg_active_w"]`` is present.
      2. The legacy flat ``hosted_gpu_hourly_usd`` rate (cloud-equivalent).

    Returns ``(rate_usd_per_hour, method_tag)`` where ``method_tag`` flows
    into the database ``cost_method`` column for traceability.  When the
    measured-power path is taken, the tag becomes
    ``local_measured:<machine>`` so the dashboard can render the real
    active/idle watts in the Method column.
    """
    machines = pricing.get("machines", {}) or {}
    machine_name = rule.get("machine")
    if machine_name and machine_name in machines:
        measured_w = None
        if power_metrics:
            v = power_metrics.get("avg_active_w")
            if v is not None and v > 0:
                measured_w = float(v)
        rate, _ = _machine_hourly_rate(
            machine_name, machines[machine_name],
            measured_avg_watts=measured_w,
        )
        if measured_w is not None:
            return rate, f"local_measured:{machine_name}"
        return rate, f"local_calendar_amortized:{machine_name}"
    fallback = float(pricing.get("hosted_gpu_hourly_usd", 1.50))
    return fallback, "cloud_equivalent_amortized"


def is_self_hosted(model: str, config: dict | None = None) -> bool:
    """Return True iff the model resolves to a ``self_hosted: true`` rule."""
    rule = _resolve_pricing(model, _pricing_block(config))
    return bool(rule and rule.get("self_hosted"))


def compute_cost(
    model: str,
    prompt_tokens: int | None,
    output_tokens: int | None,
    elapsed_s: float | None,
    *,
    cache_read_tokens: int | None = 0,
    cache_write_tokens: int | None = 0,
    config: dict | None = None,
    power_metrics: dict | None = None,
) -> tuple[float | None, str]:
    """
    Return (cost_usd, cost_method) for one query.

    * Hosted API models use the per-token rates from ``model_pricing.models``.
      Anthropic-style prompt-cache traffic is priced separately:

        - cache reads default to ``cache_read_per_mtok`` if present in the
          rule, otherwise 10% of ``input_per_mtok`` (Anthropic 5-min TTL).
        - cache writes default to ``cache_write_per_mtok`` if present,
          otherwise 125% of ``input_per_mtok`` (Anthropic 5-min TTL).

    * Self-hosted SLMs (``self_hosted: true``) are billed for ``elapsed_s``
      seconds at the hourly rate of their referenced machine, which is in
      turn computed from capex amortization + average power × $/kWh.
    * Models with no pricing rule but a known elapsed time fall back to the
      legacy cloud-equivalent flat rate as a placeholder.
    * If we have neither pricing nor elapsed_s, returns (None, "unknown").
    """
    pricing = _pricing_block(config)
    rule = _resolve_pricing(model, pricing)

    if rule and rule.get("self_hosted"):
        if elapsed_s is None or elapsed_s <= 0:
            return None, "self_hosted_no_latency"
        hourly, method = _resolve_self_hosted_hourly(
            rule, pricing, power_metrics=power_metrics,
        )
        return (elapsed_s / 3600.0) * hourly, method

    if rule:
        in_rate = float(rule.get("input_per_mtok", 0.0))
        out_rate = float(rule.get("output_per_mtok", 0.0))
        cache_read_rate = float(rule.get(
            "cache_read_per_mtok", in_rate * 0.10))
        cache_write_rate = float(rule.get(
            "cache_write_per_mtok", in_rate * 1.25))
        pin = max(int(prompt_tokens or 0), 0)
        pout = max(int(output_tokens or 0), 0)
        cread = max(int(cache_read_tokens or 0), 0)
        cwrite = max(int(cache_write_tokens or 0), 0)
        cost = (
            (pin    / 1_000_000.0) * in_rate
          + (pout   / 1_000_000.0) * out_rate
          + (cread  / 1_000_000.0) * cache_read_rate
          + (cwrite / 1_000_000.0) * cache_write_rate
        )
        method = "api_priced_with_cache" if (cread or cwrite) else "api_priced"
        return cost, method

    # Unknown model: best-effort cloud-equivalent amortization as a placeholder
    if elapsed_s is not None and elapsed_s > 0:
        hourly = float(pricing.get("hosted_gpu_hourly_usd", 1.50))
        return (elapsed_s / 3600.0) * hourly, "cloud_equivalent_amortized_unknown_model"
    return None, "unknown"


def describe_machines(config: dict | None = None) -> dict[str, dict]:
    """
    Return ``{machine_name: breakdown}`` for every machine in
    ``model_pricing.machines``.  Convenient for dashboard footnotes that
    want to disclose the assumed capex / power / electricity numbers.
    """
    pricing = _pricing_block(config)
    machines = pricing.get("machines", {}) or {}
    out: dict[str, dict] = {}
    for name, cfg in machines.items():
        _, breakdown = _machine_hourly_rate(name, cfg)
        breakdown = dict(breakdown)
        if "description" in cfg:
            breakdown["description"] = cfg["description"]
        out[name] = breakdown
    return out


def chars_per_token(config: dict | None = None) -> float:
    """Return the configured chars-per-token estimation factor."""
    pricing = _pricing_block(config)
    return float(pricing.get("estimation_chars_per_token", 3.5))


def tokens_per_sec(
    output_tokens: int | None,
    elapsed_s: float | None,
) -> float | None:
    """Throughput in output-tokens per wall-clock second."""
    if not output_tokens or output_tokens <= 0:
        return None
    if not elapsed_s or elapsed_s <= 0:
        return None
    return float(output_tokens) / float(elapsed_s)


def annotate_with_cost(
    model: str,
    usage: dict[str, Any] | None,
    elapsed_s: float | None,
    *,
    config: dict | None = None,
    power_metrics: dict | None = None,
) -> dict[str, Any]:
    """
    Convenience: turn a raw usage dict into the full set of cost/token
    columns the harness writes to the database.
    """
    usage = usage or {}
    prompt_tokens = usage.get("prompt_tokens")
    output_tokens = usage.get("output_tokens")
    total_tokens = usage.get("total_tokens")
    cache_read_tokens = usage.get("cache_read_tokens") or 0
    cache_write_tokens = usage.get("cache_write_tokens") or 0
    estimated = bool(usage.get("estimated", False))
    cost_usd, cost_method = compute_cost(
        model, prompt_tokens, output_tokens, elapsed_s,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        config=config,
        power_metrics=power_metrics,
    )
    return {
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "cache_read_tokens": int(cache_read_tokens or 0),
        "cache_write_tokens": int(cache_write_tokens or 0),
        "tokens_estimated": 1 if estimated else 0,
        "tokens_per_sec": tokens_per_sec(output_tokens, elapsed_s),
        "cost_usd": cost_usd,
        "cost_method": cost_method,
    }
