import requests
import traceback
from datetime import datetime, timezone, timedelta

from get_data import db

# -------- CONFIG --------
BLYNK_TOKEN = "GjGmM6wxg_ko6sn3m4gFbMEYYDmdTTIU"
BLYNK_URL = "https://blynk.cloud/external/api/update"

IST = timezone(timedelta(hours=5, minutes=30))

# -------- BLYNK WRITE --------
def blynk_write(pin, value):
    try:
        url = f"{BLYNK_URL}?token={BLYNK_TOKEN}&{pin}={value}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            print(f"✅ Blynk {pin} = {value}")
        else:
            print(f"❌ Blynk error on {pin}: {response.text}")

    except Exception as e:
        print(f"❌ Blynk request failed: {e}")

# -------- CALCULATE TODAY STATS ONLY --------
def calculate_stats():
    try:
        today_ist = datetime.now(IST).strftime("%Y-%m-%d")
        print(f"🕐 Today (IST): {today_ist}")

        # -------- FETCH DATA --------
        data = db.child("PostureData").get().val()

        if not data:
            print("⚠️ No data in Firebase")
            return

        # -------- FILTER TODAY ONLY --------
        today_entries = [
            e for e in data.values()
            if e.get("timestamp", "").startswith(today_ist)
        ]

        # ❗ STRICT: no fallback
        if not today_entries:
            print("⚠️ No entries for today — skipping stats")
            return

        entries = today_entries
        total = len(entries)

        print(f"📅 Today's entries: {total}")

        # -------- SORT --------
        sorted_entries = sorted(
            entries,
            key=lambda x: x.get("timestamp", "")
        )

        # -------- LATEST ENTRY --------
        latest = sorted_entries[-1]
        angle1 = latest.get("sensor1", {}).get("angle", 0)
        angle2 = latest.get("sensor2", {}).get("angle", 0)

        print(f"📐 Latest — A1: {angle1:.1f}° A2: {angle2:.1f}°")

        # -------- POSTURE SCORE --------
        posture_score = 100 - int((angle1 + angle2) / 2.0 * 100.0 / 45.0)
        posture_score = max(0, min(100, posture_score))

        # -------- GOOD POSTURE % --------
        good_count = sum(
            1 for e in entries
            if e.get("sensor1", {}).get("angle", 0) <= 20
            and e.get("sensor2", {}).get("angle", 0) <= 20
        )
        daily_pct = int(good_count * 100 / total)

        # -------- CURRENT BAD DURATION --------
        bad_streak_count = 0
        for e in reversed(sorted_entries):
            a1 = e.get("sensor1", {}).get("angle", 0)
            a2 = e.get("sensor2", {}).get("angle", 0)

            if a1 > 20 or a2 > 20:
                bad_streak_count += 1
            else:
                break

        bad_duration_mins = int(bad_streak_count * 5 / 60)

        # -------- LONGEST BAD STREAK --------
        longest_streak = 0
        current_streak = 0

        for e in sorted_entries:
            a1 = e.get("sensor1", {}).get("angle", 0)
            a2 = e.get("sensor2", {}).get("angle", 0)

            if a1 > 20 or a2 > 20:
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            else:
                current_streak = 0

        longest_streak_mins = int(longest_streak * 5 / 60)

        # -------- TOTAL BAD COUNT --------
        total_bad = sum(
            1 for e in entries
            if e.get("sensor1", {}).get("angle", 0) > 20
            or e.get("sensor2", {}).get("angle", 0) > 20
        )

        # -------- AVERAGE BACK ANGLE --------
        avg_angle1 = sum(
            e.get("sensor1", {}).get("angle", 0) for e in entries
        ) / total

        # -------- STATUS --------
        is_bad = angle1 > 20 or angle2 > 20
        status = "Bad Posture" if is_bad else "Good Posture"

        # -------- PRINT SUMMARY --------
        print(f"\n📊 Today's Summary:")
        print(f"   Status:          {status}")
        print(f"   Score:           {posture_score}")
        print(f"   Daily Good:      {daily_pct}%")
        print(f"   Bad Duration:    {bad_duration_mins} mins")
        print(f"   Longest Streak:  {longest_streak_mins} mins")
        print(f"   Total Bad:       {total_bad}")
        print(f"   Avg Back Angle:  {avg_angle1:.1f}°")

        # -------- WRITE TO FIREBASE --------
        db.child("Stats").set({
            "postureScore": posture_score,
            "dailyGoodPct": daily_pct,
            "badDurationMins": bad_duration_mins,
            "longestStreakMins": longest_streak_mins,
            "totalBadReadings": total_bad,
            "totalGoodReadings": good_count,
            "avgBackAngle": round(avg_angle1, 1),
            "currentStatus": "Bad" if is_bad else "Good",
            "lastUpdated": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
        })

        print("✅ Stats updated (today only)")

        # -------- SEND TO BLYNK --------
        blynk_write("v0", round(angle1, 1))                 # Back angle
        blynk_write("v1", round(angle2, 1))                 # Neck angle
        blynk_write("v2", status)                           # Status
        blynk_write("v3", posture_score)                    # Score
        blynk_write("v4", f"{bad_duration_mins} mins")      # Current bad duration
        blynk_write("v5", f"{avg_angle1:.1f}")              # Avg angle
        blynk_write("v6", f"{daily_pct}%")                  # Good %
        blynk_write("v7", f"{longest_streak_mins} mins")    # Longest streak

    except Exception as e:
        print(f"❌ Error calculating stats: {e}")
        traceback.print_exc()

if __name__ == '__main__':
    print("🚀 SpineSense (Today-only stats)...")
    calculate_stats()
    print("✅ Done")
