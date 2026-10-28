"""Public research records stay separate from explicitly authored model assumptions."""
from hashlib import sha256
from pathlib import Path
import math
from numbers import Real

import pandas as pd

from kol_data import REQUIRED_FIELDS, RESEARCH_ASSUMPTION_VERSION, validate_kol_data
from portfolio import cents

DATA_DIR = Path(__file__).resolve().parent / "data"
RESEARCH_PATH = DATA_DIR / "real_kols.csv"
ASSUMPTIONS_PATH = DATA_DIR / "mock_campaign_assumptions.csv"
RESEARCH_FIELDS = (
    "creator_id", "creator_name", "handle", "platform", "profile_url", "creator_category",
    "fit_rationale", "fit_assessment_type", "followers", "follower_count_checked_at",
    "source_url", "source_data_date", "source_date_basis", "reported_followers",
    "follower_count_notes", "recent_post_url", "recent_post_date", "recent_content_source_url",
    "visible_likes", "visible_comments", "visible_views", "observed_engagement_rate",
    "engagement_rate_basis", "us_audience_share", "us_audience_evidence",
    "petkit_collaboration_evidence", "competitor_collaboration_evidence", "verification_status",
    "verification_tier", "manual_review_fields", "notes", "research_checked_at", "identity_data_type",
)
PARAMETER_MAP = {
    "estimated_fee_usd": "estimated_fee_usd", "estimated_reach": "estimated_reach",
    "assumed_engagement_rate": "engagement_rate", "assumed_ctr": "assumed_ctr",
    "assumed_cvr": "assumed_click_to_purchase_cvr",
    "assumed_audience_match_score": "audience_match_score",
    "assumed_content_quality_score": "content_quality_score",
}
ASSUMPTION_FIELDS = ("creator_id", "model_enabled", "model_data_type", "assumption_version",
                     "planning_basis", "exclusion_reason", *PARAMETER_MAP,
                     *(f"{field}_source" for field in PARAMETER_MAP))


def _read(path, required):
    try:
        data = pd.read_csv(path)
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeError) as exc:
        raise ValueError(f"Unable to read research/assumption CSV: {exc}") from exc
    missing = sorted(set(required) - set(data.columns))
    if missing:
        raise ValueError("Missing research/assumption fields: " + ", ".join(missing))
    if data.empty:
        raise ValueError("Research/assumption CSV is empty.")
    if data.creator_id.isna().any() or data.creator_id.astype(str).str.strip().eq("").any() or data.creator_id.duplicated().any():
        raise ValueError("Research/assumption creator_id must be non-blank and unique.")
    return data


def load_real_kols(path=RESEARCH_PATH):
    data = _read(path, RESEARCH_FIELDS)
    forbidden = set(PARAMETER_MAP) | {"engagement_rate", "audience_match_score", "content_quality_score", "assumption_version"}
    if forbidden.intersection(data.columns):
        raise ValueError("Simulated planning parameters must not be stored in the public research table.")
    for field in ("creator_name", "handle", "platform", "profile_url", "creator_category", "source_url", "manual_review_fields"):
        if data[field].isna().any() or data[field].astype(str).str.strip().eq("").any():
            raise ValueError(f"Public research {field} must not be blank.")
    if not data.identity_data_type.eq("public_profile").all():
        raise ValueError("Research identity_data_type must be public_profile.")
    if not data.verification_status.isin(["partially_verified", "unverified"]).all():
        raise ValueError("This approved report does not establish any fully verified creators.")
    if not data.verification_tier.isin(["A", "B"]).all():
        raise ValueError("verification_tier must be A or B.")
    if not data.fit_assessment_type.eq("researcher_interpretation").all():
        raise ValueError("Fit rationale is a researcher interpretation, not an observed fact.")
    numeric_bounds = {"followers": (1, 10_000_000), "reported_followers": (1, 10_000_000),
                      "visible_likes": (0, 1_000_000_000), "visible_comments": (0, 1_000_000_000),
                      "visible_views": (0, 1_000_000_000), "observed_engagement_rate": (0, 10),
                      "us_audience_share": (0, 1)}
    for field, (lower, upper) in numeric_bounds.items():
        original = data[field]
        numeric = pd.to_numeric(original, errors="coerce")
        present = original.notna()
        if numeric[present].isna().any() or not numeric[present].map(math.isfinite).all() or not numeric[present].between(lower, upper).all():
            raise ValueError(f"Invalid public research numeric field: {field}")
        data[field] = numeric
    if data.loc[data.followers.notna(), ["source_data_date", "follower_count_checked_at"]].isna().any().any():
        raise ValueError("Observed followers require a source date and checked date.")
    if data.loc[data.observed_engagement_rate.notna(), "engagement_rate_basis"].isna().any():
        raise ValueError("Observed engagement requires denominator, sample and time-window evidence.")
    if data.loc[data.us_audience_share.notna(), "us_audience_evidence"].isna().any():
        raise ValueError("US audience estimates require evidence.")
    return data


def load_campaign_assumptions(path=ASSUMPTIONS_PATH):
    data = _read(path, ASSUMPTION_FIELDS)
    enabled = data.model_enabled.astype(str).str.lower().map({"true": True, "false": False})
    if enabled.isna().any():
        raise ValueError("model_enabled must be true or false.")
    data["model_enabled"] = enabled
    if not data.model_data_type.eq("simulated").all():
        raise ValueError("All campaign assumptions must be labeled simulated.")
    if not data.assumption_version.eq(RESEARCH_ASSUMPTION_VERSION).all():
        raise ValueError("Unexpected research planning assumption version.")
    return data


def prepare_research_model(research, assumptions):
    """Left join by ID; no observed-field fallback, imputation or positional matching.

    Return an audit table for all identities and a validated numeric model subset.
    Metadata travels with model rows into scores, forecasts and CSV export.
    """
    if research.creator_id.duplicated().any() or assumptions.creator_id.duplicated().any():
        raise ValueError("Join requires unique creator_id in both tables.")
    unknown = set(assumptions.creator_id) - set(research.creator_id)
    if unknown:
        raise ValueError("Assumptions reference unknown creator_id: " + ", ".join(sorted(unknown)))
    joined = research.merge(assumptions, on="creator_id", how="left", validate="one_to_one")
    accepted, reasons = [], []
    for _, row in joined.iterrows():
        problems = []
        if pd.isna(row.model_enabled) or not bool(row.model_enabled):
            problems.append("Model disabled or no assumption row; " + (str(row.exclusion_reason) if pd.notna(row.exclusion_reason) else "parameters require explicit configuration"))
        for field in PARAMETER_MAP:
            value = row[field]
            if pd.isna(value):
                problems.append("Missing " + field)
            elif not isinstance(value, Real) or not math.isfinite(value):
                problems.append("Invalid " + field)
            if pd.isna(row[f"{field}_source"]) or not str(row[f"{field}_source"]).strip():
                problems.append("Missing parameter source: " + field)
        if row.model_data_type != "simulated" or row.assumption_version != RESEARCH_ASSUMPTION_VERSION:
            problems.append("Model provenance/version is invalid")
        if pd.isna(row.planning_basis) or not str(row.planning_basis).strip():
            problems.append("Planning basis is missing")
        model = row.to_dict()
        for source, target in PARAMETER_MAP.items():
            model[target] = row[source]
        model.update(data_type="hybrid_public_identity_simulated_model", numeric_score_basis="simulated_preset")
        if not problems:
            try:
                valid = validate_kol_data(pd.DataFrame([model]))
                cents(valid.iloc[0].estimated_fee_usd, "Creator fee")
                accepted.append(valid)
            except ValueError as exc:
                problems.append(str(exc))
        reasons.append("; ".join(problems) if problems else "Model inputs complete; SIMULATED planning only. Booking and US audience remain unverified.")
    joined["model_eligibility_reason"] = reasons
    joined["model_eligible"] = [reason.startswith("Model inputs complete") for reason in reasons]
    model_data = pd.concat(accepted, ignore_index=True) if accepted else pd.DataFrame(columns=REQUIRED_FIELDS)
    return joined, model_data


def research_fingerprint(research, assumptions):
    payload = "research-adapter-v1" + research.sort_values("creator_id").to_csv(index=False) + assumptions.sort_values("creator_id").to_csv(index=False)
    return sha256(payload.encode("utf-8")).hexdigest()
