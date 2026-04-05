import traceback
from datetime import datetime, timezone, timedelta, date
from get_data import db

IST = timezone(timedelta(hours=5, minutes=30))

# ── Risk thresholds (flex ADC values) ──────────────────────────────────────
# Back  → flex1 | Neck → flex2
BACK_MILD     = 700
BACK_MODERATE = 1500
BACK_SEVERE   = 2500

NECK_MILD     = 700
NECK_MODERATE = 1500
NECK_SEVERE   = 2500

# ── Side effects by risk level ─────────────────────────────────────────────
SIDE_EFFECTS = {
    "Low": [
        "Occasional muscle fatigue",
        "Minor stiffness after long sessions"
    ],
    "Moderate": [
        "Chronic neck/back tension",
        "Headaches and eye strain",
        "Reduced spinal flexibility",
        "Increased risk of muscle imbalance"
    ],
    "High": [
        "Cervical spondylosis risk",
        "Lumbar disc pressure",
        "Nerve compression (tingling/numbness)",
        "Persistent muscle spasms",
        "Long-term postural deformity risk"
    ],
    "Critical": [
        "Herniated disc risk",
        "Chronic pain syndrome",
        "Nerve damage potential",
        "Severe spinal misalignment",
        "Requires immediate physiotherapy"
    ]
}


def _risk_level(bad_pct: float) -> str:
    if bad_pct < 20:
        return "Low"
    elif bad_pct < 45:
        return "Moderate"
    elif bad_pct < 70:
        return "High"
    return "Critical"


def _score_from_pct(bad_pct: float) -> int:
    """0 = worst, 100 = best"""
    return max(0, min(100, int(100 - bad_pct)))


def _analyse_entries(entries: list) -> dict:
    """Core analysis on a list of Firebase PostureData entries (dicts)."""
    total = len(entries)
    if total == 0:
        return {}

    back_bad = sum(
        1 for e in entries
        if e.get("sensor1", {}).get("adc", e.get("flex1", 0)) > BACK_MILD
    )
    neck_bad = sum(
        1 for e in entries
        if e.get("sensor2", {}).get("adc", e.get("flex2", 0)) > NECK_MILD
    )
    both_bad = sum(
        1 for e in entries
        if e.get("sensor1", {}).get("adc", e.get("flex1", 0)) > BACK_MILD
        and e.get("sensor2", {}).get("adc", e.get("flex2", 0)) > NECK_MILD
    )

    back_bad_pct  = round(back_bad  * 100 / total, 1)
    neck_bad_pct  = round(neck_bad  * 100 / total, 1)
    total_aff_pct = round(
        sum(
            1 for e in entries
            if e.get("sensor1", {}).get("adc", e.get("flex1", 0)) > BACK_MILD
            or e.get("sensor2", {}).get("adc", e.get("flex2", 0)) > NECK_MILD
        ) * 100 / total, 1
    )

    back_risk  = _risk_level(back_bad_pct)
    neck_risk  = _risk_level(neck_bad_pct)
    total_risk = _risk_level(total_aff_pct)

    # Worst of back/neck drives the side-effects shown
    risk_priority = ["Critical", "High", "Moderate", "Low"]
    dominant_risk = next(r for r in risk_priority if r in (back_risk, neck_risk, total_risk))

    return {
        "totalReadings":    total,
        "backRiskPct":      back_bad_pct,
        "backRiskLevel":    back_risk,
        "backRiskScore":    _score_from_pct(back_bad_pct),
        "neckRiskPct":      neck_bad_pct,
        "neckRiskLevel":    neck_risk,
        "neckRiskScore":    _score_from_pct(neck_bad_pct),
        "totalAffectedPct": total_aff_pct,
        "totalRiskLevel":   total_risk,
        "bothAffectedPct":  round(both_bad * 100 / total, 1),
        "sideEffects":      SIDE_EFFECTS[dominant_risk],
        "dominantRisk":     dominant_risk,
    }


def _fetch_all_today(today_str: str) -> list:
    data = db.child("PostureData").get().val()
    if not data:
        return []
    return [
        v for v in data.values()
        if isinstance(v, dict) and v.get("timestamp", "").startswith(today_str)
    ]


def _fetch_date_range(start_date: date, end_date: date) -> list:
    """Fetch all entries between start_date and end_date (inclusive)."""
    data = db.child("PostureData").get().val()
    if not data:
        return []
    entries = []
    current = start_date
    while current <= end_date:
        prefix = current.strftime("%Y-%m-%d")
        entries.extend(
            v for v in data.values()
            if isinstance(v, dict) and v.get("timestamp", "").startswith(prefix)
        )
        current += timedelta(days=1)
    return entries


# ── Public API ─────────────────────────────────────────────────────────────

def analyse_risk():
    """
    Runs daily, weekly, and monthly risk analysis and writes all results
    to Firebase under RiskAnalysis/{daily|weekly|monthly}.
    """
    try:
        now       = datetime.now(IST)
        today_str = now.strftime("%Y-%m-%d")
        today_d   = now.date()

        print(f"\n🧠 Running Risk Analysis — {today_str}")

        # ── DAILY ──────────────────────────────────────────────────────────
        daily_entries = _fetch_all_today(today_str)
        if not daily_entries:
            print("⚠️  No data for today — skipping risk analysis")
            return

        daily = _analyse_entries(daily_entries)
        daily["period"]      = "daily"
        daily["date"]        = today_str
        daily["lastUpdated"] = now.strftime("%Y-%m-%d %H:%M:%S")

        db.child("RiskAnalysis").child("daily").set(daily)
        print(f"✅ Daily   — Back: {daily['backRiskLevel']} | "
              f"Neck: {daily['neckRiskLevel']} | "
              f"Total affected: {daily['totalAffectedPct']}%")

        # ── WEEKLY ─────────────────────────────────────────────────────────
        week_start  = today_d - timedelta(days=today_d.weekday())   # Monday
        week_entries = _fetch_date_range(week_start, today_d)

        weekly = _analyse_entries(week_entries)
        weekly["period"]      = "weekly"
        weekly["weekStart"]   = week_start.strftime("%Y-%m-%d")
        weekly["weekEnd"]     = today_str
        weekly["lastUpdated"] = now.strftime("%Y-%m-%d %H:%M:%S")

        db.child("RiskAnalysis").child("weekly").set(weekly)
        print(f"✅ Weekly  — Back: {weekly['backRiskLevel']} | "
              f"Neck: {weekly['neckRiskLevel']} | "
              f"Total affected: {weekly['totalAffectedPct']}%")

        # ── MONTHLY ────────────────────────────────────────────────────────
        month_start   = today_d.replace(day=1)
        month_entries = _fetch_date_range(month_start, today_d)

        monthly = _analyse_entries(month_entries)
        monthly["period"]      = "monthly"
        monthly["monthStart"]  = month_start.strftime("%Y-%m-%d")
        monthly["monthEnd"]    = today_str
        monthly["lastUpdated"] = now.strftime("%Y-%m-%d %H:%M:%S")

        db.child("RiskAnalysis").child("monthly").set(monthly)
        print(f"✅ Monthly — Back: {monthly['backRiskLevel']} | "
              f"Neck: {monthly['neckRiskLevel']} | "
              f"Total affected: {monthly['totalAffectedPct']}%")

        _print_summary(daily, "TODAY")

    except Exception as e:
        print(f"❌ Risk analysis error: {e}")
        traceback.print_exc()


def _print_summary(result: dict, label: str):
    print(f"\n📋 Risk Summary — {label}")
    print(f"   Back Risk    : {result['backRiskLevel']}  ({result['backRiskPct']}% bad readings, score {result['backRiskScore']}/100)")
    print(f"   Neck Risk    : {result['neckRiskLevel']}  ({result['neckRiskPct']}% bad readings, score {result['neckRiskScore']}/100)")
    print(f"   Total Affected: {result['totalAffectedPct']}%  →  {result['totalRiskLevel']}")
    print(f"   Dominant Risk : {result['dominantRisk']}")
    print(f"   ⚠️  Side Effects if continued:")
    for fx in result["sideEffects"]:
        print(f"      • {fx}")


if __name__ == "__main__":
    analyse_risk()
