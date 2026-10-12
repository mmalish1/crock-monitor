#!/usr/bin/env python3
"""
Reads the crock water level from a JSN-SR04T ultrasonic sensor on a Raspberry Pi
and logs each reading to a SQLite database.

The sensor is mounted above the crock pointing down, so it measures the distance
to the water surface. If CROCK_EMPTY_DISTANCE_CM (sensor face to crock bottom) is
set, the water depth is also calculated: level = empty distance - measured distance.

Usage:
    python3 crock_level.py          # log a reading every CROCK_INTERVAL_SECONDS
    python3 crock_level.py --once   # print one reading and exit (wiring test)
"""
import argparse
import os
import signal
import sqlite3
import statistics
import sys
import time
import warnings
from datetime import datetime, timezone

from gpiozero import DistanceSensor
from gpiozero.exc import PWMSoftwareFallback

# gpiozero suggests the pigpio pin factory for better timing, but pigpio doesn't
# support the Pi 5. The median over several samples smooths out the jitter instead.
warnings.filterwarnings("ignore", category=PWMSoftwareFallback)

TRIGGER_PIN = int(os.environ.get("CROCK_TRIGGER_PIN", "23"))
ECHO_PIN = int(os.environ.get("CROCK_ECHO_PIN", "24"))
EMPTY_DISTANCE_CM = float(os.environ.get("CROCK_EMPTY_DISTANCE_CM", "0"))
INTERVAL_SECONDS = float(os.environ.get("CROCK_INTERVAL_SECONDS", "60"))
SAMPLES_PER_READING = int(os.environ.get("CROCK_SAMPLES", "15"))
DB_PATH = os.environ.get("CROCK_DB_PATH", os.path.expanduser("~/crock-level.db"))

# The JSN-SR04T can't see anything closer than ~25cm (its "blind zone"), and we
# don't need to look further than this. Readings outside the range are dropped.
MIN_DISTANCE_CM = 25.0
MAX_DISTANCE_M = 2.0


def open_db(path):
    db = sqlite3.connect(path)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            recorded_at  TEXT    NOT NULL,  -- ISO 8601, UTC
            distance_cm  REAL    NOT NULL,  -- sensor face to water surface
            level_cm     REAL,              -- water depth, NULL if empty distance not configured
            sample_count INTEGER NOT NULL   -- valid samples that went into the median
        )
        """
    )
    db.commit()
    return db


def take_reading(sensor):
    """Take several samples and return (median distance in cm, valid sample count)."""
    samples = []
    for _ in range(SAMPLES_PER_READING):
        distance_cm = sensor.distance * 100
        # gpiozero reports max_distance when no echo comes back, so treat that as invalid too.
        if MIN_DISTANCE_CM <= distance_cm < MAX_DISTANCE_M * 100 * 0.99:
            samples.append(distance_cm)
        time.sleep(0.1)

    if not samples:
        return None, 0
    return statistics.median(samples), len(samples)


def level_from_distance(distance_cm):
    if EMPTY_DISTANCE_CM <= 0:
        return None
    return max(0.0, EMPTY_DISTANCE_CM - distance_cm)


def main():
    parser = argparse.ArgumentParser(description="Log crock water level from a JSN-SR04T sensor.")
    parser.add_argument("--once", action="store_true", help="print one reading and exit")
    args = parser.parse_args()

    # systemd stops the service with SIGTERM; turn it into a normal exit so the
    # sensor and database get closed cleanly.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    sensor = DistanceSensor(echo=ECHO_PIN, trigger=TRIGGER_PIN, max_distance=MAX_DISTANCE_M)
    db = None if args.once else open_db(DB_PATH)
    try:
        # Give gpiozero's background thread time to fill its sample queue.
        time.sleep(1)
        while True:
            distance_cm, sample_count = take_reading(sensor)
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")

            if distance_cm is None:
                print(f"{now} no valid echo (check wiring, or water is inside the 25cm blind zone)", flush=True)
            else:
                level_cm = level_from_distance(distance_cm)
                level_text = f", level {level_cm:.1f} cm" if level_cm is not None else ""
                print(f"{now} distance {distance_cm:.1f} cm{level_text} ({sample_count} samples)", flush=True)
                if db is not None:
                    db.execute(
                        "INSERT INTO readings (recorded_at, distance_cm, level_cm, sample_count) VALUES (?, ?, ?, ?)",
                        (now, round(distance_cm, 1), None if level_cm is None else round(level_cm, 1), sample_count),
                    )
                    db.commit()

            if args.once:
                break
            time.sleep(INTERVAL_SECONDS)
    finally:
        sensor.close()
        if db is not None:
            db.close()


if __name__ == "__main__":
    main()
