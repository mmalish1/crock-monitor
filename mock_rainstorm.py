#!/usr/bin/env python3
"""
Generates mock crock water level readings for a rainstorm, in the same JSON shape
crock_level.py posts to the Pioneer API.

The model: water seeps in slowly before the storm, rain pushes the inflow up to a
peak and then tapers off, and the sump pump switches on at a high water mark and
drains the crock to a low mark. The simulation runs second by second, and a
reading is taken every READING_INTERVAL_SECONDS like the real script.

Usage:
    python3 mock_rainstorm.py                   # writes mock-rainstorm.json
    python3 mock_rainstorm.py -o storm.json     # writes to another file
    python3 mock_rainstorm.py --seed 7 --account "Storm 2 Data" --post
                                                # a different storm, also sent to the API
    python3 mock_rainstorm.py --scenario emergency
                                                # the pump can't keep up and the crock overflows
    python3 mock_rainstorm.py --scenario emergency --include-high-water
                                                # same, with readings the real sensor couldn't take
"""
import argparse
import json
import math
import os
import random
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

DEFAULT_START = "2026-10-14T18:00:00Z"
DURATION_HOURS = 5
READING_INTERVAL_SECONDS = 15
API_URL = os.environ.get("CROCK_API_URL", "https://tybodager-001-site9.gtempurl.com/Pioneer")
API_TIMEOUT_SECONDS = 15

# The sensor is 40cm above the crock bottom and can't see closer than 25cm, so the
# deepest water it can measure is 15cm. The pump float switches inside that range.
MAX_MEASURABLE_CM = 15.0
PUMP_ON_CM = 12.5
PUMP_OFF_CM = 4.0
PUMP_RATE_CM_PER_MIN = 30.0
STARTING_LEVEL_CM = 3.5

# Inflow in cm of crock depth per minute.
SEEPAGE_CM_PER_MIN = 0.02
STORM_START_MIN = 60
STORM_PEAK_MIN = 135
STORM_END_MIN = 240
STORM_PEAK_CM_PER_MIN = 2.0
# In the emergency scenario the rain at its heaviest comes in faster than the pump
# can remove it, so the pump runs nonstop and the water still rises.
EMERGENCY_PEAK_CM_PER_MIN = 36.0
# Where the water spills over the top of the crock onto the floor.
CROCK_RIM_CM = 30.0

SENSOR_NOISE_CM = 0.25

SCENARIOS = {
    "storm": {"peak_cm_per_min": STORM_PEAK_CM_PER_MIN, "account": "Storm 1 Data", "output": "mock-rainstorm.json"},
    "emergency": {
        "peak_cm_per_min": EMERGENCY_PEAK_CM_PER_MIN,
        "account": "Emergency 1 Data",
        "output": "mock-emergency.json",
    },
}


def rain_inflow(minute, peak_cm_per_min):
    """Inflow from the storm: ramps up to the peak, then tails off more slowly."""
    if minute < STORM_START_MIN:
        return 0.0
    if minute < STORM_PEAK_MIN:
        x = (minute - STORM_START_MIN) / (STORM_PEAK_MIN - STORM_START_MIN)
        return peak_cm_per_min * math.sin(x * math.pi / 2) ** 2
    if minute < STORM_END_MIN:
        x = (minute - STORM_PEAK_MIN) / (STORM_END_MIN - STORM_PEAK_MIN)
        return peak_cm_per_min * math.cos(x * math.pi / 2) ** 2
    # Ground water keeps draining in for a while after the rain stops.
    return 0.15 * math.exp(-(minute - STORM_END_MIN) / 20)


def simulate(seed, start, account_name, peak_cm_per_min, include_high_water=False):
    """Returns (readings, stats). Like the real sensor, no reading is produced while
    the water is above MAX_MEASURABLE_CM, unless include_high_water is set."""
    rng = random.Random(seed)
    level = STARTING_LEVEL_CM
    pump_on = False
    readings = []
    stats = {"pump_cycles": 0, "highest_cm": level, "blind_seconds": 0, "overflow_seconds": 0}

    for second in range(DURATION_HOURS * 3600):
        minute = second / 60
        # Gusty rain: the inflow wobbles around the storm curve.
        inflow = SEEPAGE_CM_PER_MIN + rain_inflow(minute, peak_cm_per_min) * rng.uniform(0.7, 1.3)
        outflow = PUMP_RATE_CM_PER_MIN if pump_on else 0.0
        level = min(CROCK_RIM_CM, max(0.0, level + (inflow - outflow) / 60))

        stats["highest_cm"] = max(stats["highest_cm"], level)
        if level > MAX_MEASURABLE_CM:
            stats["blind_seconds"] += 1
        if level >= CROCK_RIM_CM:
            stats["overflow_seconds"] += 1

        if not pump_on and level >= PUMP_ON_CM:
            pump_on = True
            stats["pump_cycles"] += 1
        elif pump_on and level <= PUMP_OFF_CM:
            pump_on = False

        if second % READING_INTERVAL_SECONDS == 0:
            measured = max(0.0, level + rng.gauss(0, SENSOR_NOISE_CM))
            if measured > MAX_MEASURABLE_CM and not include_high_water:
                continue
            at = start + timedelta(seconds=second)
            readings.append(
                {
                    "id": 0,
                    "sensorType": "CrockMonitor",
                    "dateTime": at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                    "accountName": account_name,
                    "dataKey": "WaterLevel",
                    "dataValue": f"{measured:.1f}",
                }
            )

    return readings, stats


def post_readings(readings):
    """Send each reading to the API. Retries network errors, but stops at the first
    error response, since the rest would most likely be rejected the same way."""
    for i, reading in enumerate(readings, 1):
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(reading).encode("utf-8"),
            headers={"accept": "*/*", "Content-Type": "application/json"},
            method="POST",
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=API_TIMEOUT_SECONDS):
                    break
            except urllib.error.HTTPError as error:
                body = error.read(300).decode("utf-8", errors="replace")
                raise SystemExit(f"Reading {i} was rejected: HTTP {error.code} {body}")
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                if attempt == 2:
                    raise SystemExit(f"Reading {i} failed after 3 tries: {error}")
                time.sleep(2)
        if i % 200 == 0 or i == len(readings):
            print(f"Sent {i} of {len(readings)}", flush=True)


def main():
    parser = argparse.ArgumentParser(description="Generate mock rainstorm crock readings.")
    parser.add_argument(
        "--scenario",
        choices=SCENARIOS,
        default="storm",
        help="storm: the pump keeps up. emergency: the rain outpaces the pump and the crock overflows",
    )
    parser.add_argument("-o", "--output", help="default: mock-rainstorm.json or mock-emergency.json")
    parser.add_argument("--seed", type=int, default=42, help="change for a different storm")
    parser.add_argument("--account", help="accountName sent with each reading (default depends on the scenario)")
    parser.add_argument("--start", default=DEFAULT_START, help="UTC time of the first reading, e.g. 2026-10-20T18:00:00Z")
    parser.add_argument("--post", action="store_true", help="also send the readings to the API")
    parser.add_argument(
        "--include-high-water",
        action="store_true",
        help=f"keep readings above {MAX_MEASURABLE_CM:.0f}cm, as if the sensor were mounted higher",
    )
    args = parser.parse_args()

    scenario = SCENARIOS[args.scenario]
    output = args.output or scenario["output"]
    account = args.account or scenario["account"]
    start = datetime.fromisoformat(args.start.replace("Z", "+00:00")).astimezone(timezone.utc)
    readings, stats = simulate(args.seed, start, account, scenario["peak_cm_per_min"], args.include_high_water)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(readings, f, indent=2)

    levels = [float(r["dataValue"]) for r in readings]
    print(f"Wrote {len(readings)} readings to {output}")
    print(f"{readings[0]['dateTime']} to {readings[-1]['dateTime']}")
    print(f"Pump ran {stats['pump_cycles']} times, readings ranged {min(levels):.1f} to {max(levels):.1f} cm")
    if stats["blind_seconds"]:
        print(
            f"Water was above the sensor's {MAX_MEASURABLE_CM:.0f}cm limit for {stats['blind_seconds'] / 60:.0f} min "
            f"({'included anyway' if args.include_high_water else 'no readings then'}), peaked at {stats['highest_cm']:.1f} cm, "
            f"overflowed the crock for {stats['overflow_seconds'] / 60:.0f} min"
        )

    if args.post:
        print(f"Sending to {API_URL} as account \"{account}\"", flush=True)
        post_readings(readings)


if __name__ == "__main__":
    main()
