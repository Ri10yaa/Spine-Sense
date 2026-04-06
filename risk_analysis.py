"""
risk_analysis.py — End-of-day batch posture risk pipeline.

Runs once per day at EOD_RUN_TIME (default 23:55 IST).

Pipeline:
  PostureData/ (today's entries)
      → compute_daily()          → PostureResult/daily/YYYY_MM_DD
      → compute_weekly_from_daily() → PostureResult/weekly/YYYY_Wxx
      → compute_monthly_from_daily() → PostureResult/monthly/YYYY_MM
  State: PostureResult/meta/lastEODRun = YYYY-MM-DD
"""

import os
import logging
import traceback
from collections import defaultdict
from datetime import datetime, timezone, timedelta, date

from get_data import db

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger("risk_analysis")

# ── Config ─────────────────────────────────────────────────────────────────
IST            = timezone(timedelta(hours=5, minutes=30))
BACK_THRESHOLD = 700
NECK_THRESHOLD = 700
EOD_RUN_TIME   = os.getenv("EOD_RUN_TIME", "23:55")  # HH:MM IST
EOD_WINDOW_MIN = 5   # minutes the window stays open

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

RISK_PRIORITY = ["Critical", "High", "Moderate", "Low"]

# In-memory guard — prevents duplicate runs within the same process session
_last_eod_run: str = ""


# ── Pure helpers ───────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(IST)

def _today_str() -> str:
    return _now().strftime("%Y-%m-%d")

def _safe(day_str: str) -> str:
    return day_str.replace("-", "_")

def _risk_level(bad_pct: float) -> str:
    if bad_pct < 20:  return "Low"
    if bad_pct < 45:  return "Moderate"
    if bad_pct < 70:  return "High"
    return "Critical"

def _dominant_risk(*levels: str) -> str:
    for r in RISK_PRIORITY:
        if r in levels:
            return r
    return "Low"

def _pct(count: int, total: int) -> float:
    return round(count * 100 / total, 1) if total else 0.0

def _score(bad_pct: float) -> int:
    return max(0, min(100, int(100 - bad_pct)))

def _now_str() -> str:
    return _now().strftime("%Y-%m-%d %H:%M:%S")

def _build_risk_block(total: int, back_bad: int, neck_bad: int,
                      both_bad: int, either_bad: int) -> dict:
    back_pct  = _pct(back_bad,   total)
    neck_pct  = _pct(neck_bad,   total)
    total_pct = _pct(either_bad, total)
    back_lvl  = _risk_level(back_pct)
    neck_lvl  = _risk_level(neck_pct)
    total_lvl = _risk_level(total_pct)
    dominant  = _dominant_risk(back_lvl, neck_lvl, total_lvl)
    return {
        "totalReadings":    total,
        "backBadCount":     back_bad,
        "neckBadCount":     neck_bad,
        "bothBadCount":     both_bad,
        "eitherBadCount":   either_bad,
        "backRiskPct":      back_pct,
        "neckRiskPct":      neck_pct,
        "totalAffectedPct": total_pct,
        "bothAffectedPct":  _pct(both_bad, total),
        "backRiskLevel":    back_lvl,
        "backRiskScore":    _score(back_pct),
        "neckRiskLevel":    neck_lvl,
        "neckRiskScore":    _score(neck_pct),
        "totalRiskLevel":   total_lvl,
        "dominantRisk":     dominant,
        "sideEffects":      SIDE_EFFECTS[dominant],
    }


# ── Firebase I/O ───────────────────────────────────────────────────────────

def _fb_get(path: str):
    try:
        return db.child(path).get().val()
    except Exception as e:
        log.error(f"Firebase GET failed [{path}]: {e}")
        return None

def _fb_set(path: str, data: dict):
    try:
        db.child(path).set(data)
        log.info(f"Pushed → {path}")
    except Exception as e:
        log.error(f"Firebase SET failed [{path}]: {e}")


# ── Step 1: Fetch today's raw data ────────────────────────────────────────

def fetch_today_data(today: str) -> list:
    """Fetch today's entries. Tries structured path first, then flat fallback."""
    log.info(f"Fetching raw data for {today}...")

    node = _fb_get(f"PostureData/{today}")
    if node and isinstance(node, dict):
        entries = list(node.values())
        log.info(f"  {len(entries)} entries from PostureData/{today}/")
        return entries

    # Flat fallback for legacy data structure
    log.warning("Structured path not found — using flat filtered read")
    raw = _fb_get("PostureData")
    if not raw:
        log.warning("No PostureData found")
        return []
    entries = [
        v for v in raw.values()
        if isinstance(v, dict) and v.get("timestamp", "").startswith(today)
    ]
    log.info(f"  {len(entries)} entries for {today} (flat fallback)")
    return entries


# ── Step 2: Compute daily aggregate ───────────────────────────────────────

def compute_daily(entries: list, today: str) -> dict:
    """Compute full daily risk aggregate from raw sensor entries."""
    total = len(entries)
    if total == 0:
        log.warning(f"No entries to compute daily for {today}")
        return {}

    back_bad   = sum(1 for e in entries if e.get("sensor1", {}).get("adc", 0) > BACK_THRESHOLD)
    neck_bad   = sum(1 for e in entries if e.get("sensor2", {}).get("adc", 0) > NECK_THRESHOLD)
    both_bad   = sum(
        1 for e in entries
        if e.get("sensor1", {}).get("adc", 0) > BACK_THRESHOLD
        and e.get("sensor2", {}).get("adc", 0) > NECK_THRESHOLD
    )
    either_bad = sum(
        1 for e in entries
        if e.get("sensor1", {}).get("adc", 0) > BACK_THRESHOLD
        or e.get("sensor2", {}).get("adc", 0) > NECK_THRESHOLD
    )

    result = _build_risk_block(total, back_bad, neck_bad, both_bad, either_bad)
    result.update({"period": "daily", "date": today, "lastUpdated": _now_str()})

    log.info(f"Daily {today} — Back: {result['backRiskLevel']} | "
             f"Neck: {result['neckRiskLevel']} | "
             f"Affected: {result['totalAffectedPct']}% | Readings: {total}")
    return result


# ── Step 3: Fetch stored daily results for a set of dates ─────────────────

def _fetch_daily_results_for(day_keys: list) -> list:
    """
    Fetch specific daily results from PostureResult/daily/.
    day_keys: list of safe keys e.g. ['2026_04_01', '2026_04_02']
    O(n_days_in_period) — no full scan.
    """
    results = []
    for key in day_keys:
        result = _fb_get(f"PostureResult/daily/{key}")
        if result and isinstance(result, dict):
            results.append(result)
        else:
            log.debug(f"No daily result found for {key}")
    return results


# ── Step 4: Batch weekly aggregation from daily results ───────────────────

def compute_weekly_from_daily(today: str) -> dict:
    """
    Fetch all daily results for the current ISO week and recompute weekly aggregate.
    O(n_days_in_week) — max 7 Firebase reads.
    """
    d        = date.fromisoformat(today)
    iso      = d.isocalendar()
    week_key = f"{iso[0]}_W{iso[1]:02d}"

    # Build list of dates in this ISO week up to today
    week_start = d - timedelta(days=d.weekday())  # Monday
    day_keys   = [
        _safe((week_start + timedelta(days=i)).isoformat())
        for i in range((d - week_start).days + 1)
    ]

    log.info(f"Weekly {week_key} — fetching {len(day_keys)} daily result(s)...")
    daily_results = _fetch_daily_results_for(day_keys)

    if not daily_results:
        log.warning(f"No daily results found for week {week_key}")
        return {}

    total      = sum(r.get("totalReadings",  0) for r in daily_results)
    back_bad   = sum(r.get("backBadCount",   0) for r in daily_results)
    neck_bad   = sum(r.get("neckBadCount",   0) for r in daily_results)
    both_bad   = sum(r.get("bothBadCount",   0) for r in daily_results)
    either_bad = sum(r.get("eitherBadCount", 0) for r in daily_results)

    result = _build_risk_block(total, back_bad, neck_bad, both_bad, either_bad)
    result.update({"period": "weekly", "week": week_key, "lastUpdated": _now_str()})

    log.info(f"Weekly {week_key} — {total} readings, dominant: {result['dominantRisk']}")
    return result


# ── Step 5: Batch monthly aggregation from daily results ──────────────────

def compute_monthly_from_daily(today: str) -> dict:
    """
    Fetch all daily results for the current month and recompute monthly aggregate.
    O(n_days_in_month) — max 31 Firebase reads.
    """
    d         = date.fromisoformat(today)
    month_key = today[:7].replace("-", "_")

    # Build list of dates from 1st of month to today
    month_start = d.replace(day=1)
    day_keys    = [
        _safe((month_start + timedelta(days=i)).isoformat())
        for i in range((d - month_start).days + 1)
    ]

    log.info(f"Monthly {month_key} — fetching {len(day_keys)} daily result(s)...")
    daily_results = _fetch_daily_results_for(day_keys)

    if not daily_results:
        log.warning(f"No daily results found for month {month_key}")
        return {}

    total      = sum(r.get("totalReadings",  0) for r in daily_results)
    back_bad   = sum(r.get("backBadCount",   0) for r in daily_results)
    neck_bad   = sum(r.get("neckBadCount",   0) for r in daily_results)
    both_bad   = sum(r.get("bothBadCount",   0) for r in daily_results)
    either_bad = sum(r.get("eitherBadCount", 0) for r in daily_results)

    result = _build_risk_block(total, back_bad, neck_bad, both_bad, either_bad)
    result.update({"period": "monthly", "month": month_key, "lastUpdated": _now_str()})

    log.info(f"Monthly {month_key} — {total} readings, dominant: {result['dominantRisk']}")
    return result


# ── Step 6: End-of-day pipeline ───────────────────────────────────────────

def run_end_of_day_pipeline():
    """
    Full end-of-day batch pipeline. Runs once per day at EOD_RUN_TIME.
      1. Compute daily from today's raw data
      2. Compute weekly by fetching this week's daily results
      3. Compute monthly by fetching this month's daily results
      4. Push all three to Firebase
    """
    today = _today_str()
    log.info(f"=== End-of-Day Pipeline — {today} ===")

    # Daily
    entries = fetch_today_data(today)
    if not entries:
        log.warning(f"No raw data for {today} — aborting pipeline")
        return

    daily = compute_daily(entries, today)
    if not daily:
        log.warning("Daily computation failed — aborting pipeline")
        return
    _fb_set(f"PostureResult/daily/{_safe(today)}", daily)

    # Weekly (batch from stored daily results)
    weekly = compute_weekly_from_daily(today)
    if weekly:
        iso  = date.fromisoformat(today).isocalendar()
        _fb_set(f"PostureResult/weekly/{iso[0]}_W{iso[1]:02d}", weekly)

    # Monthly (batch from stored daily results)
    monthly = compute_monthly_from_daily(today)
    if monthly:
        _fb_set(f"PostureResult/monthly/{today[:7].replace('-', '_')}", monthly)

    log.info(f"=== End-of-Day Pipeline complete — {today} ===")


# ── Scheduler ─────────────────────────────────────────────────────────────

def run_end_of_day_if_scheduled():
    """
    Called every minute from main loop.
    Triggers run_end_of_day_pipeline() only if:
      - Current IST time is within EOD_RUN_TIME window
      - Has not already run today (checked in-memory + Firebase)
    """
    global _last_eod_run

    now       = _now()
    today_str = now.strftime("%Y-%m-%d")

    # In-memory guard
    if _last_eod_run == today_str:
        return

    # Parse schedule
    try:
        sched_h, sched_m = map(int, EOD_RUN_TIME.split(":"))
    except ValueError:
        log.error(f"Invalid EOD_RUN_TIME: '{EOD_RUN_TIME}' — expected HH:MM")
        return

    window_start = now.replace(hour=sched_h, minute=sched_m, second=0, microsecond=0)
    window_end   = window_start + timedelta(minutes=EOD_WINDOW_MIN)

    if not (window_start <= now < window_end):
        return  # Not time yet — silent, no log spam

    # Firebase guard — survives restarts
    last_run = _fb_get("PostureResult/meta/lastEODRun")
    if last_run == today_str:
        log.info(f"EOD pipeline already ran today ({today_str}) — skipping")
        _last_eod_run = today_str
        return

    log.info(f"⏰ EOD pipeline triggered at {now.strftime('%H:%M:%S')} IST")

    try:
        run_end_of_day_pipeline()
        _fb_set("PostureResult/meta/lastEODRun", today_str)
        _last_eod_run = today_str
        log.info(f"✅ EOD run recorded — next run at {EOD_RUN_TIME} IST tomorrow")
    except Exception as e:
        log.error(f"EOD pipeline failed: {e}")
        traceback.print_exc()


# ── Backwards-compatible entry point (called from main.py) ────────────────

def analyse_risk():
    run_end_of_day_if_scheduled()


# ── Manual / backfill entry point ─────────────────────────────────────────

def run_backfill():
    """
    One-time historical backfill.
    Processes all dates found in PostureData/ that don't yet have a daily result.
    Run manually: python risk_analysis.py backfill
    """
    log.info("=== Historical Backfill ===")

    raw = _fb_get("PostureData")
    if not raw:
        log.warning("No PostureData found")
        return

    by_date = defaultdict(list)
    for entry in raw.values():
        if not isinstance(entry, dict):
            continue
        ts  = entry.get("timestamp", "")
        day = ts[:10] if len(ts) >= 10 else None
        if day:
            by_date[day].append(entry)

    log.info(f"Found {len(by_date)} day(s): {sorted(by_date.keys())}")

    for day_str in sorted(by_date.keys()):
        safe_key = _safe(day_str)
        existing = _fb_get(f"PostureResult/daily/{safe_key}")
        if existing:
            log.info(f"Skipping {day_str} — already processed")
            continue

        daily = compute_daily(by_date[day_str], day_str)
        if not daily:
            continue
        _fb_set(f"PostureResult/daily/{safe_key}", daily)

    # Rebuild weekly + monthly for all processed dates
    all_daily = _fb_get("PostureResult/daily") or {}
    weeks, months = set(), set()
    for key, result in all_daily.items():
        day_str = result.get("date", key.replace("_", "-"))
        try:
            d = date.fromisoformat(day_str)
            iso = d.isocalendar()
            weeks.add((day_str, f"{iso[0]}_W{iso[1]:02d}"))
            months.add((day_str, day_str[:7].replace("-", "_")))
        except ValueError:
            continue

    for day_str, week_key in weeks:
        weekly = compute_weekly_from_daily(day_str)
        if weekly:
            _fb_set(f"PostureResult/weekly/{week_key}", weekly)

    done_months = set()
    for day_str, month_key in sorted(months, reverse=True):
        if month_key in done_months:
            continue
        monthly = compute_monthly_from_daily(day_str)
        if monthly:
            _fb_set(f"PostureResult/monthly/{month_key}", monthly)
            done_months.add(month_key)

    log.info("=== Backfill complete ===")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "backfill":
        run_backfill()
    elif len(sys.argv) > 1 and sys.argv[1] == "force":
        # Force run pipeline immediately regardless of schedule
        run_end_of_day_pipeline()
    else:
        run_end_of_day_if_scheduled()
