"""Budget-constrained planning, transparent forecasts, snapshots and CSV export."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256

import pandas as pd

from kol_data import ASSUMPTION_VERSION, REQUIRED_FIELDS, WEIGHTS, score_kols, validate_kol_data

MODEL_VERSION = "portfolio-v1/" + ASSUMPTION_VERSION
DISCLAIMER = (
    "SIMULATED fees, forecasts and numeric fit/quality presets. Creator identities are fictional in the demo dataset "
    "and public research identities in the research dataset; partial verification is not booking readiness. US pet-tech fit proxy only. "
    "Reach is cumulative and NOT deduplicated. Conversions are mathematical expectations, "
    "not actual orders or ROI. One short video per creator. No AI API. "
    "Costs include creator fee plus per-creator sample and shipping assumptions; exclude tax, internal labor and amplification."
)
OUTCOME_COLUMNS = {"Brand Awareness": "target_reach", "Engagement": "projected_engagements", "Conversion": "projected_conversions"}
METRIC_KEYS = ("budget_usd", "spent_usd", "remaining_usd", "creator_count", "raw_reach", "target_reach", "engagements", "clicks", "conversions", "cpm_usd", "cpe_usd", "cpc_usd", "cpa_usd")


def cents(value, name="cost"):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount != amount.quantize(Decimal("0.01")):
            raise ValueError
        return int(amount * 100)
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(f"{name} must be a finite non-negative USD amount with at most two decimal places.") from None


def eligible_candidates(data):
    """Reject invalid rows and all duplicate IDs rather than inventing missing inputs."""
    missing = set(REQUIRED_FIELDS) - set(data.columns)
    if missing:
        return data.iloc[:0].copy(), ["Missing required fields: " + ", ".join(sorted(missing))]
    duplicates = data.creator_id.duplicated(keep=False)
    rows, excluded = [], 0
    for index in range(len(data)):
        row = data.iloc[[index]]
        try:
            if duplicates.iloc[index]:
                raise ValueError("Duplicate ID")
            valid = validate_kol_data(row)
            cents(valid.iloc[0].estimated_fee_usd, "Creator fee")
            rows.append(valid)
        except ValueError:
            excluded += 1
    clean = pd.concat(rows, ignore_index=True) if rows else data.iloc[:0].copy()
    return clean, ([f"Excluded {excluded} invalid or duplicate creator records."] if excluded else [])


def forecast_creators(scored, sample_usd=0, shipping_usd=0):
    extra = cents(sample_usd, "Sample cost") + cents(shipping_usd, "Shipping cost")
    result = scored.copy()
    result["execution_cost_usd"] = result["estimated_fee_usd"].map(lambda value: (cents(value) + extra) / 100)
    result["raw_reach"] = result["estimated_reach"]
    result["target_reach"] = result["raw_reach"] * result["audience_match_score"] / 100
    result["projected_engagements"] = result["target_reach"] * result["engagement_rate"]
    result["projected_clicks"] = result["target_reach"] * result["assumed_ctr"]
    result["projected_conversions"] = result["projected_clicks"] * result["assumed_click_to_purchase_cvr"]
    return result


def summarize(selected, budget):
    budget_cents = cents(budget, "Budget")
    def total(column):
        return float(selected[column].sum()) if column in selected and not selected.empty else 0.0
    spent_cents = sum(cents(value) for value in selected.get("execution_cost_usd", []))
    if spent_cents > budget_cents:
        raise ValueError("Portfolio exceeds the campaign budget.")
    metrics = dict(budget_usd=budget_cents / 100, spent_usd=spent_cents / 100,
                   remaining_usd=(budget_cents - spent_cents) / 100, creator_count=len(selected),
                   raw_reach=total("raw_reach"), target_reach=total("target_reach"),
                   engagements=total("projected_engagements"), clicks=total("projected_clicks"),
                   conversions=total("projected_conversions"))
    for key, denominator, multiplier in (("cpm_usd", "target_reach", 1000), ("cpe_usd", "engagements", 1), ("cpc_usd", "clicks", 1), ("cpa_usd", "conversions", 1)):
        metrics[key] = metrics["spent_usd"] * multiplier / metrics[denominator] if metrics[denominator] > 0 else None
    return metrics


@dataclass
class PortfolioResult:
    selected: pd.DataFrame
    candidates: pd.DataFrame
    metrics: dict
    messages: list[str]


def optimize_portfolio(data, budget, objective="Brand Awareness", sample_usd=0, shipping_usd=0, max_creators=6):
    """Exact 0/1 knapsack DP with count constraint and integer-cent costs.

    Maximize cumulative target outcome, not the sum of individual ranking scores.
    Ties: lower total cost, then lexicographic creator IDs.
    """
    budget_cents = cents(budget, "Budget")
    if budget_cents > 1_000_000:
        raise ValueError("Demo budget must not exceed $10,000.")
    if objective not in WEIGHTS:
        raise ValueError(f"Unknown campaign objective: {objective}")
    if not isinstance(max_creators, int) or not 1 <= max_creators <= 6:
        raise ValueError("Maximum creators must be an integer from 1 to 6.")
    cents(sample_usd, "Sample cost")
    cents(shipping_usd, "Shipping cost")
    clean, messages = eligible_candidates(data)
    if len(clean) > 30:
        raise ValueError("This demo supports at most 30 candidate creators.")
    scored = score_kols(clean, objective) if not clean.empty else clean
    candidates = forecast_creators(scored, sample_usd, shipping_usd) if not clean.empty else pd.DataFrame()
    # (count, cost) -> (objective value, ordered IDs). Copy each iteration enforces 0/1 use.
    states = {(0, 0): (0.0, ())}
    outcome_column = OUTCOME_COLUMNS[objective]
    if not candidates.empty:
        for _, row in candidates.sort_values("creator_id").iterrows():
            cost, value = cents(row.execution_cost_usd), float(row[outcome_column])
            updated = states.copy()
            for (count, spent), (benefit, ids) in states.items():
                if count >= max_creators or spent + cost > budget_cents or value <= 0:
                    continue
                key, proposal = (count + 1, spent + cost), (benefit + value, ids + (row.creator_id,))
                previous = updated.get(key)
                if previous is None or proposal[0] > previous[0] or (proposal[0] == previous[0] and proposal[1] < previous[1]):
                    updated[key] = proposal
            states = updated
    _, best = min(states.items(), key=lambda item: (-item[1][0], item[0][1], item[1][1]))
    selected = candidates[candidates.creator_id.isin(best[1])].copy() if not candidates.empty else candidates.copy()
    if selected.empty:
        messages.append("No feasible positive-outcome portfolio: check filters, budget and per-creator execution costs.")
    else:
        selected["selection_reason"] = selected.apply(lambda row: (
            f"Part of the maximum {objective} outcome portfolio under the budget and {max_creators}-creator limit; "
            f"contributes {row[outcome_column]:,.2f} simulated outcome units at ${row.execution_cost_usd:,.2f}. "
            f"Individual score {row.total_score:.2f}/100; not selected by score order."
        ), axis=1)
    return PortfolioResult(selected, candidates, summarize(selected, budget), messages)


def model_fingerprint(data):
    return sha256((MODEL_VERSION + data.sort_values("creator_id").to_csv(index=False)).encode()).hexdigest()


def make_snapshot(result, campaign, fingerprint):
    return {"campaign": dict(campaign), "fingerprint": fingerprint,
            "metrics": dict(result.metrics), "selected_ids": result.selected.get("creator_id", pd.Series(dtype=str)).tolist()}


def compare_scenarios(baseline, current):
    if baseline["fingerprint"] != current["fingerprint"]:
        raise ValueError("Data or model assumptions changed. Save a new baseline before comparing.")
    rows = []
    for key in METRIC_KEYS:
        old, new = baseline["metrics"][key], current["metrics"][key]
        delta = new - old if old is not None and new is not None else None
        percent = delta / old * 100 if delta is not None and old != 0 else None
        rows.append(dict(metric=key, baseline=old, current=new, absolute_change=delta, percent_change=percent))
    return pd.DataFrame(rows)


def export_portfolio_csv(result, campaign):
    """One selected creator per row; portfolio totals repeat and must not be summed."""
    if result.selected.empty:
        raise ValueError("No recommended creators to export.")
    output = result.selected.copy()
    for key, value in campaign.items():
        output[f"campaign_{key}"] = value
    for key, value in result.metrics.items():
        output[f"portfolio_{key}"] = value
    output["model_version"] = MODEL_VERSION
    output["simulation_notice"] = DISCLAIMER
    output["forecast_formulas"] = "target_reach=estimated_reach*audience_match_score/100; engagements=target_reach*ER; clicks=target_reach*CTR; conversions=clicks*CVR; CPM=spent/target_reach*1000; CPE/CPC/CPA=spent/corresponding_outcome; zero denominator=N/A"
    output["export_note"] = "Portfolio totals repeat per creator; do not sum portfolio_* columns."
    # Keep free text inert when opened by Excel, including user-entered campaign labels.
    for column in output.select_dtypes(include=["str", "object"]).columns:
        output[column] = output[column].map(lambda value: "'" + value if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")) else value)
    return output.to_csv(index=False).encode("utf-8-sig")
