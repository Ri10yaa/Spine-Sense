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
_pending_queue  = []
_queue_lock     = threading.Lock()
_listener       = None
_processed_keys = set()     # tracks all keys already written to postureresult
_listener_ready = False     # prevents double-connect snapshot firing


def load_processed_keys_from_firebase():
    """
    On startup, read postureresult from Firebase and populate
    _processed_keys so already-written entries are never reprocessed
    even across restarts.
    """
    global _processed_keys
    try:
        data = db.child("postureresult").get().val()
        if data and isinstance(data, dict):
            with _queue_lock:
                _processed_keys = set(data.keys())
            print(f"🔑 Loaded {len(_processed_keys)} already-processed keys from Firebase.")
        else:
            print("🔑 No existing postureresult entries found.")
    except Exception as e:
        print(f"❌ Failed to load processed keys: {e}")


def mark_processed(key):
    """Call this from main.py after successfully writing to postureresult."""
    with _queue_lock:
        _processed_keys.add(key)


def _on_firebase_event(message):
    global _listener_ready
    try:
        data = message.get("data")
        path = message.get("path", "")

        if not data or not isinstance(data, dict):
            return

        today = datetime.now().strftime("%Y-%m-%d")

        if path == "/":
            # Guard against Pyrebase firing the initial snapshot twice
            if _listener_ready:
                return
            _listener_ready = True

            entries = [
                (key, value)
                for key, value in data.items()
                if isinstance(value, dict)
                and value.get("timestamp", "").startswith(today)
                and key not in _processed_keys
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
                and key not in _processed_keys
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
    Real-time mode: pop the oldest entry from the listener queue one at a time.
    Called in a drain loop by main — processes all queued entries in order.
    """
    with _queue_lock:
        if not _pending_queue:
            return None

        key, item = _pending_queue.pop(0)   # oldest first, one at a time

    if key in _processed_keys:
        return None

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
                and key not in _processed_keys      # skip already processed
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