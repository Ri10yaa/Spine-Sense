import time
import csv
import os
import pyrebase
from dotenv import load_dotenv

from get_data import (
    collect_data_realtime,
    collect_data_backlog,
    start_listener,
    stop_listener
)
from predict_posture import predict_posture
from calculate_stats import calculate_stats
from risk_analysis import analyse_risk

load_dotenv()

config = {
    "apiKey": os.getenv("FIREBASE_API_KEY"),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.getenv("FIREBASE_DB_URL"),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET")
}

firebase = pyrebase.initialize_app(config)
db = firebase.database()

OUTPUT_FILE = "flex_data.csv"

REALTIME_INTERVAL  = 1      # seconds
BACKLOG_INTERVAL   = 300    # seconds (5 minutes)
SCHEDULER_INTERVAL = 60     # seconds (1 minute — EOD scheduler tick)

if not os.path.exists(OUTPUT_FILE):
    with open(OUTPUT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "flex1", "flex2", "posture"])


def update_posture_firebase(key, posture):
    try:
        db.child("PostureData").child(key).update({"posture": posture})
        print(f"✅ Updated {key} → {posture}")
    except Exception as e:
        print(f"❌ Firebase update failed: {e}")


def process(result, source):
    if not result:
        return
    key, timestamp, flex1, flex2 = result
    posture = predict_posture(flex1, flex2)
    print(f"[{source}] Flex1: {flex1} | Flex2: {flex2} | Posture: {posture}")
    with open(OUTPUT_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, flex1, flex2, posture])
    update_posture_firebase(key, posture)


print("🚀 Starting Spine-Sense... (Ctrl+C to stop)")
print(f"   Real-time check : every {REALTIME_INTERVAL}s  (listener-based)")
print(f"   Backlog sweep   : every {BACKLOG_INTERVAL}s")

# Start listener — runs in background thread, pushes to queue instantly
start_listener()

# Give listener 2 seconds to connect and load initial snapshot
time.sleep(2)

last_backlog_time   = time.time()
last_scheduler_time = time.time()

try:
    while True:
        now = time.time()

        # ---- BACKLOG SWEEP (every 5 minutes) ----
        if now - last_backlog_time >= BACKLOG_INTERVAL:
            print("\n🔄 Running backlog sweep...")
            processed = 0
            while True:
                result = collect_data_backlog()
                if not result:
                    break
                process(result, "BACKLOG")
                processed += 1
            print(f"✅ Backlog sweep done — {processed} entries processed.\n")

            print("\n📊 Calculating and syncing statistics...")
            calculate_stats()

            last_backlog_time = time.time()

        # ---- DAILY RISK SCHEDULER (every 1 minute) ----
        if now - last_scheduler_time >= SCHEDULER_INTERVAL:
            analyse_risk()
            last_scheduler_time = time.time()

        # ---- REAL-TIME CHECK (every 1 second) ----
        try:
            result = collect_data_realtime()
            process(result, "LIVE")
        except Exception as e:
            print(f"❌ Real-time cycle error: {e}")

        time.sleep(REALTIME_INTERVAL)

except KeyboardInterrupt:
    stop_listener()
    print("\n🛑 Stopped by user.")
except Exception as e:
    stop_listener()
    print(f"\n❌ Fatal error: {e}")
