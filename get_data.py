import pyrebase
import csv
import os
import threading
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

config = {
    "apiKey": os.getenv("FIREBASE_API_KEY"),
    "authDomain": os.getenv("FIREBASE_AUTH_DOMAIN"),
    "databaseURL": os.getenv("FIREBASE_DB_URL"),
    "storageBucket": os.getenv("FIREBASE_STORAGE_BUCKET")
}

firebase = pyrebase.initialize_app(config)
db = firebase.database()

RAW_FILE = "data_raw.csv"

if not os.path.exists(RAW_FILE):
    with open(RAW_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "flex1", "flex2"])

# ---- SHARED STATE ----
_pending_queue = []
_queue_lock    = threading.Lock()
_listener      = None


def _on_firebase_event(message):
    """
    Called instantly by Firebase whenever a child is added or changed.
    Filters to only unprocessed entries for today.
    """
    try:
        data  = message.get("data")
        path  = message.get("path", "")

        if not data or not isinstance(data, dict):
            return

        today = datetime.now().strftime("%Y-%m-%d")

        if path == "/":
            # Initial full snapshot on connect — queue all unprocessed today entries
            entries = [
                (key, value)
                for key, value in data.items()
                if isinstance(value, dict)
                and value.get("timestamp", "").startswith(today)
                and "posture" not in value
            ]
            entries.sort(key=lambda x: x[1].get("timestamp", ""))

            with _queue_lock:
                _pending_queue.clear()
                _pending_queue.extend(entries)

            print(f"📡 Listener connected — {len(entries)} unprocessed entries queued.")

        else:
            # Single new or updated child event
            key = path.strip("/")

            if (
                isinstance(data, dict)
                and data.get("timestamp", "").startswith(today)
                and "posture" not in data
            ):
                with _queue_lock:
                    existing_keys = [k for k, _ in _pending_queue]
                    if key not in existing_keys:
                        _pending_queue.append((key, data))

                print(f"📡 New entry detected: {key}")

    except Exception as e:
        print(f"❌ Listener error: {e}")


def start_listener():
    """Start Firebase real-time listener in background thread."""
    global _listener
    _listener = db.child("PostureData").stream(_on_firebase_event)
    print("📡 Firebase listener started.")


def stop_listener():
    """Stop the Firebase real-time listener."""
    global _listener
    if _listener:
        _listener.close()
        print("📡 Firebase listener stopped.")


def _build_result(key, item):
    """Extract fields and log to raw CSV."""
    flex1     = item["sensor1"]["adc"]
    flex2     = item["sensor2"]["adc"]
    timestamp = item.get("timestamp")

    with open(RAW_FILE, "a", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, flex1, flex2])

    print(f"📍 Processing: {key} | flex1={flex1}, flex2={flex2}")
    return key, timestamp, flex1, flex2


def collect_data_realtime():
    """
    Real-time mode: pop the latest entry from the listener queue.
    Returns it if unprocessed, otherwise None.
    Called every 1 second by main loop.
    """
    with _queue_lock:
        if not _pending_queue:
            return None

        # Take the latest entry, drop any older stale ones
        key, item = _pending_queue[-1]
        _pending_queue.clear()

    try:
        return _build_result(key, item)
    except Exception as e:
        print(f"❌ Real-time build error: {e}")
        return None


def collect_data_backlog():
    """
    Backlog mode: full DB read to find oldest unprocessed entry.
    Returns one entry per call — loop until None.
    Called every 5 minutes by main loop.
    """
    try:
        data = db.child("PostureData").get().val()
        if not data:
            return None

        today = datetime.now().strftime("%Y-%m-%d")

        today_items = sorted(
            [
                (key, value)
                for key, value in data.items()
                if isinstance(value, dict)
                and value.get("timestamp", "").startswith(today)
                and "posture" not in value
            ],
            key=lambda x: x[1].get("timestamp", "")
        )

        if not today_items:
            return None

        key, item = today_items[0]  # oldest unprocessed first
        return _build_result(key, item)

    except Exception as e:
        print(f"❌ Backlog fetch error: {e}")
        return None