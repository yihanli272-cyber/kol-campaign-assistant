"""Validated simulated creator data and deterministic, brand-independent scoring."""
from pathlib import Path
import math

import pandas as pd

DATA_PATH = Path(__file__).resolve().parent / "data" / "mock_kols.csv"
ASSUMPTION_VERSION = "phase1-v1"
RESEARCH_ASSUMPTION_VERSION = "research-planning-v1"
WEIGHTS = {
    "Brand Awareness": dict(audience=0.30, reach=0.35, engagement=0.10, quality=0.15, efficiency=0.10),
    "Engagement": dict(audience=0.25, reach=0.10, engagement=0.30, quality=0.15, efficiency=0.20),
    "Conversion": dict(audience=0.30, reach=0.05, engagement=0.05, quality=0.20, efficiency=0.40),
}
# Fixed demonstration caps; never recalculated from filtered candidates.
EFFICIENCY_CAPS = {"Brand Awareness": 100.0, "Engagement": 8.0, "Conversion": 0.04}
RANGES = {
    "followers": (1, 10_000_000), "engagement_rate": (0, 1),
    "audience_match_score": (0, 100), "estimated_reach": (0, 10_000_000),
    "estimated_fee_usd": (1, 1_000_000), "content_quality_score": (0, 100),
    "assumed_ctr": (0, 1), "assumed_click_to_purchase_cvr": (0, 1),
}
REQUIRED_FIELDS = (
    "creator_id", "creator_name", "platform", "creator_category", *RANGES,
    "data_type", "assumption_version",
)


def validate_kol_data(data: pd.DataFrame) -> pd.DataFrame:
    """Return a cleaned copy, or a clear ValueError for invalid input."""
    missing = sorted(set(REQUIRED_FIELDS) - set(data.columns))
    if missing:
        raise ValueError("Missing required fields: " + ", ".join(missing))
    if data.empty:
        raise ValueError("KOL data is empty; at least one creator is required.")
    result = data.copy()
    hybrid = result["data_type"].eq("hybrid_public_identity_simulated_model")
    if not (hybrid | result["data_type"].eq("simulated")).all():
        raise ValueError("data_type must be simulated or hybrid_public_identity_simulated_model.")
    if hybrid.any():
        for field, expected in {"identity_data_type": "public_profile", "model_data_type": "simulated",
                                "numeric_score_basis": "simulated_preset"}.items():
            if field not in result or not result.loc[hybrid, field].eq(expected).all():
                raise ValueError(f"Hybrid records require {field}={expected}.")
    for field, (lower, upper) in RANGES.items():
        values = pd.to_numeric(result[field], errors="coerce")
        # Public follower counts may be unknown. They are not used by score/forecast math.
        optional = hybrid & result[field].isna() if field == "followers" else pd.Series(False, index=result.index)
        checked = values.loc[~optional]
        if checked.isna().any() or not checked.map(math.isfinite).all() or not checked.between(lower, upper).all():
            raise ValueError(f"{field} must contain finite numbers between {lower} and {upper}.")
        result[field] = values
    for field in ("followers", "estimated_reach"):
        if (result[field].dropna() % 1 != 0).any():
            raise ValueError(f"{field} must contain whole numbers.")
    for field in set(REQUIRED_FIELDS) - set(RANGES):
        if result[field].isna().any() or result[field].astype(str).str.strip().eq("").any():
            raise ValueError(f"{field} must not contain missing or blank values.")
    if result["creator_id"].duplicated().any():
        raise ValueError("creator_id must be unique.")
    if not result.loc[~hybrid, "assumption_version"].eq(ASSUMPTION_VERSION).all():
        raise ValueError(f"Simulated assumption_version must be {ASSUMPTION_VERSION}.")
    if not result.loc[hybrid, "assumption_version"].eq(RESEARCH_ASSUMPTION_VERSION).all():
        raise ValueError(f"Hybrid assumption_version must be {RESEARCH_ASSUMPTION_VERSION}.")
    return result


def load_kol_data(path: str | Path = DATA_PATH) -> pd.DataFrame:
    try:
        data = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
        raise ValueError(f"Unable to read KOL CSV: {exc}") from exc
    return validate_kol_data(data)


def score_kols(data: pd.DataFrame, objective: str = "Brand Awareness") -> pd.DataFrame:
    """Score each creator with fixed caps; future portfolio logic consumes this output."""
    if objective not in WEIGHTS:
        raise ValueError(f"Unknown campaign objective: {objective}")
    result = validate_kol_data(data)
    reach = result["estimated_reach"] * result["audience_match_score"] / 100
    outcome = reach
    if objective == "Engagement":
        outcome = reach * result["engagement_rate"]
    elif objective == "Conversion":
        outcome = reach * result["assumed_ctr"] * result["assumed_click_to_purchase_cvr"]
    components = {
        "audience": result["audience_match_score"],
        "reach": (reach / 100_000 * 100).clip(0, 100),
        "engagement": (result["engagement_rate"] / 0.10 * 100).clip(0, 100),
        "quality": result["content_quality_score"],
        "efficiency": (outcome / result["estimated_fee_usd"] / EFFICIENCY_CAPS[objective] * 100).clip(0, 100),
    }
    for name, values in components.items():
        result[f"{name}_score"] = values
        result[f"{name}_contribution"] = values * WEIGHTS[objective][name]
    result["total_score"] = sum(result[f"{name}_contribution"] for name in components)
    result["recommendation_reason"] = result.apply(recommendation_reason, axis=1)
    return result.sort_values(["total_score", "creator_id"], ascending=[False, True]).reset_index(drop=True)


def recommendation_reason(row: pd.Series) -> str:
    """Rule explanation uses only the row's simulated values."""
    if row["data_type"] == "hybrid_public_identity_simulated_model":
        return (f"Public research: {row['handle']} on {row['platform']}; verification remains {row['verification_status']}. "
                f"Research interpretation: {row['fit_rationale']} "
                f"SIMULATED model: match {row['audience_match_score']:.0f}/100, quality {row['content_quality_score']:.0f}/100, "
                f"ER by reach {row['engagement_rate']:.1%}, fee ${row['estimated_fee_usd']:,.0f}. "
                "Planning illustration only; no claim of measured performance or booking readiness.")
    return (
        f"Simulated audience match {row['audience_match_score']:.0f}/100; "
        f"content quality {row['content_quality_score']:.0f}/100; "
        f"engagement rate {row['engagement_rate']:.1%}; "
        f"fee ${row['estimated_fee_usd']:,.0f}. "
        "Individual ranking only; portfolio fit is not yet evaluated."
    )
