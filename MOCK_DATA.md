# Mock data

`mock_rainstorm.py` makes fake crock water level readings for testing the website. It
writes them to a JSON file in the same format `crock_level.py` sends to the Pioneer API,
and can send them to the API too.

It doesn't need the sensor or the Pi. Run it from this folder with `python` on Windows,
or `python3` on the Pi.

## Scenarios

| Scenario | What happens | Default account | Default file |
|---|---|---|---|
| `storm` (default) | Rain fills the crock and the pump keeps up, running about 20 times | `Storm 1 Data` | `mock-rainstorm.json` |
| `emergency` | The rain comes in faster than the pump can remove it, and the crock overflows for about 20 minutes | `Emergency 1 Data` | `mock-emergency.json` |

Each scenario covers 5 hours with a reading every 15 seconds (1,200 readings):

- **First hour:** calm, with slow seepage
- **Hours 2–4:** the storm builds to its heaviest and then tapers off
- **Last hour:** the rain has stopped and the ground drains in more slowly

## Options

| Option | Default | What it does |
|---|---|---|
| `--scenario storm` or `--scenario emergency` | `storm` | Which event to simulate |
| `-o FILE`, `--output FILE` | depends on the scenario | Where to write the JSON |
| `--seed N` | `42` | A different number gives a different storm with the same overall shape. The same number always gives the same readings. |
| `--account NAME` | depends on the scenario | `accountName` sent with each reading. Use a new name for each data set so they stay separate on the website. |
| `--start TIME` | `2026-10-14T18:00:00Z` | UTC time of the first reading |
| `--post` | off | Also send the readings to the API. Without it, the script only writes the file. |
| `--include-high-water` | off | Keep readings above 15 cm. See [High water](#high-water) below. |
| `-h`, `--help` | | Show the options |

To send to a different API, set `CROCK_API_URL` before running:

```
$env:CROCK_API_URL = "http://localhost:5000/Pioneer"     # Windows PowerShell
export CROCK_API_URL=http://localhost:5000/Pioneer        # Pi
```

## Examples

Write the normal storm to `mock-rainstorm.json` without sending anything:

```
python mock_rainstorm.py
```

Write the emergency to `mock-emergency.json` without sending anything:

```
python mock_rainstorm.py --scenario emergency
```

Make and send a second storm on a different day:

```
python mock_rainstorm.py --seed 7 --account "Storm 2 Data" --start 2026-10-20T18:00:00Z -o storm2.json --post
```

Make and send a second emergency, including the high-water readings:

```
python mock_rainstorm.py --scenario emergency --include-high-water --seed 9 --account "Emergency 2 Data" --start 2026-10-21T18:00:00Z -o emergency2.json --post
```

## Already on the website

These have already been sent. Running them again with `--post` would add every
reading a second time.

| Account | Made with |
|---|---|
| `Storm 1 Data` | `python mock_rainstorm.py --post` |
| `Emergency 1 Data` | `python mock_rainstorm.py --scenario emergency --include-high-water --post` |

Both run Oct 14, 2026, 18:00–23:00 UTC.

## Sending to the API

- The script prints its progress every 200 readings.
- If the API rejects a reading, the script stops and shows the error rather than
  sending the rest.
- If the connection drops, it retries each reading up to 3 times before stopping.
- If it stops partway, running the same command again sends everything from the
  start, so the readings it already sent would appear twice.

## High water

The sensor is 40 cm above the bottom of the crock and can't measure anything closer than
25 cm, so the deepest water it can measure is 15 cm. In a real flood, the Pi would stop
sending readings while the water is above that.

By default the emergency scenario does the same, so the website sees a gap of about 50
minutes. With `--include-high-water`, it keeps the readings up to 30 cm, as if the sensor
were mounted higher. Use that when you want the flood to show up on the website.

## Changing the simulation

The settings are at the top of `mock_rainstorm.py`:

| Setting | Value | Meaning |
|---|---|---|
| `DURATION_HOURS` | `5` | Length of the data set |
| `READING_INTERVAL_SECONDS` | `15` | Time between readings |
| `PUMP_ON_CM` / `PUMP_OFF_CM` | `12.5` / `4.0` | Water depths where the pump turns on and off |
| `PUMP_RATE_CM_PER_MIN` | `30` | How fast the pump lowers the water |
| `STARTING_LEVEL_CM` | `3.5` | Water depth at the first reading |
| `SEEPAGE_CM_PER_MIN` | `0.02` | Background inflow when it isn't raining |
| `STORM_START_MIN` / `STORM_PEAK_MIN` / `STORM_END_MIN` | `60` / `135` / `240` | When the rain starts, is heaviest and stops, in minutes from the first reading |
| `STORM_PEAK_CM_PER_MIN` | `2` | Heaviest inflow in the normal storm |
| `EMERGENCY_PEAK_CM_PER_MIN` | `36` | Heaviest inflow in the emergency. Anything above the pump rate overwhelms it. |
| `CROCK_RIM_CM` | `30` | Depth where the water spills over the top of the crock |
| `SENSOR_NOISE_CM` | `0.25` | Random jitter added to each reading |
