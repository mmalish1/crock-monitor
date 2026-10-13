# Crock water level sensor

A JSN-SR04T waterproof ultrasonic sensor mounted above the crock, pointing down at the
water. `crock_level.py` measures the distance to the water surface and logs it to SQLite.
It runs directly on the Pi (not in Docker) so it can access the GPIO pins.

## Wiring (Pi 5)

The JSN-SR04T board runs on 5V and its **Echo pin outputs 5V**. The Pi's GPIO pins are
**3.3V only**, so Echo must go through a voltage divider. Wiring Echo straight to the Pi
can damage the GPIO pin.

| JSN-SR04T board | Pi physical pin | Notes |
|---|---|---|
| 5V   | Pin 2 (5V)             | |
| GND  | Pin 6 (GND)            | |
| Trig | Pin 16 (GPIO23)        | 3.3V from the Pi is enough to trigger it |
| Echo | Pin 18 (GPIO24) via divider | see below |

Voltage divider on Echo (5V × 2k / (1k + 2k) ≈ 3.3V):

```
Echo ──[ 1kΩ ]──┬── GPIO24 (pin 18)
                │
              [ 2kΩ ]
                │
               GND
```

(1kΩ + 2.2kΩ, or 4.7kΩ + 10kΩ, also work.)

### Alternative: logic level converter instead of the divider

A 4-channel bi-directional I2C level converter (5V ↔ 3.3V) can replace the resistors.
Trig also goes through it, so the sensor gets a full 5V trigger. No code changes needed.
Use either the converter or the divider, not both.

Converter pins (check the labels on your board):

- **LV side (3.3V, Pi):** LV1, LV2, LV, GND, LV3, LV4
- **HV side (5V, JSN):** HV1, HV2, HV, GND, HV3, HV4

Each numbered channel is a pair: LV1 ↔ HV1, LV2 ↔ HV2.

| From | To |
|---|---|
| Pi pin 1 (3.3V) | Converter **LV** |
| 5V (Pi pin 2) | Converter **HV** |
| GND (Pi pin 6) | Converter **GND** (both sides, if it has two) |
| Pi pin 16 (GPIO23) | Converter **LV1** |
| Converter **HV1** | JSN Trig |
| Pi pin 18 (GPIO24) | Converter **LV2** |
| Converter **HV2** | JSN Echo |
| 5V (Pi pin 2) | JSN 5V |
| GND (Pi pin 6) | JSN GND |

**LV must be on 3.3V and HV on 5V.** If they're swapped, the Pi's GPIO pin gets 5V.

## Breadboard wiring

The Pi header and the JSN board both have male pins, so use male-to-female jumpers from
them into the breadboard, and male-to-male jumpers for hops on the breadboard. Wire it
with the Pi powered off.

Breadboard basics: in each numbered row, holes a–e are connected and f–j are connected.
The + and − rails run the length of the board (on some long boards they're split in the
middle).

**Power (both options)**

1. Pi pin 2 (5V) → + rail
2. Pi pin 6 (GND) → − rail
3. JSN 5V → + rail
4. JSN GND → − rail

**Option A: voltage divider**

5. JSN Trig → row 10, hole a
6. Pi pin 16 → row 10, hole b
7. JSN Echo → row 15, hole a
8. 1kΩ resistor (brown-black-red) from row 15, hole c → row 18, hole c
9. Pi pin 18 → row 18, hole a
10. 2kΩ resistor (red-black-red) from row 18, hole d → − rail

No 2kΩ resistor? Two 1kΩ resistors in series, or a 2.2kΩ (red-red-red), work too.

**Option B: level converter**

Plug the converter across the breadboard's center gap so each pin gets its own row, with
the LV side on one half and the HV side on the other. The header pins often come loose
and need soldering first.

5. Pi pin 1 (3.3V) → LV row. Wire it straight to that row, **not** the + rail (that's 5V).
6. + rail → HV row
7. − rail → GND row (both GND pins, if it has two)
8. Pi pin 16 → LV1 row, and JSN Trig → HV1 row
9. Pi pin 18 → LV2 row, and JSN Echo → HV2 row

The waterproof transducer plugs into the small board with its coax cable. Keep the board
itself dry and away from the crock.

## Mounting notes

- **Blind zone:** the sensor can't measure anything closer than about **25cm**. Mount it
  at least 25cm above the *highest* water level you expect, or readings will be garbage.
- **Beam width:** the beam is wide (roughly 45–75°). In a narrow crock it can bounce off
  the walls. Mount it centered and pointing straight down. A short tube around the
  transducer can help narrow the beam if readings jump around.
- **Condensation:** water droplets on the transducer face can throw off readings. The
  script takes a median of several samples to reject one-off bad readings.

## Setup on the Pi

Copy this folder to the Pi from Windows (PowerShell), replacing `<pi-user>` with your Pi
username. It asks for the Pi's password.

```
scp -r C:\Users\mmali\source\repos\crock-monitor <pi-user>@192.168.1.226:~/
```

That puts it at `~/crock-monitor` on the Pi. Run the same command again after making changes.

Raspberry Pi OS (Bookworm) already includes `gpiozero` and `lgpio`. On Lite, install them:

```
sudo apt install -y python3-gpiozero python3-lgpio
```

Test the wiring with a single reading:

```
cd ~/crock-monitor
python3 crock_level.py --once
```

Hold your hand or a book 30–100cm in front of the transducer. You should see a reasonable
distance. If you get `no valid echo`, check the wiring and the divider.

## Calibrate

With the crock empty and the sensor mounted, run `--once` and note the distance. That's
`CROCK_EMPTY_DISTANCE_CM`. Once that's set, each reading also includes the water depth
(`level_cm`).

## Run it as a service

Edit `crock-level@.service` and set `CROCK_EMPTY_DISTANCE_CM`, then:

```
sudo cp crock-level@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now crock-level@$USER
journalctl -u crock-level@$USER -f
```

It logs one reading per minute and starts again after a reboot.

## Settings (environment variables)

| Variable | Default | |
|---|---|---|
| `CROCK_TRIGGER_PIN` | `23` | BCM GPIO number |
| `CROCK_ECHO_PIN` | `24` | BCM GPIO number |
| `CROCK_EMPTY_DISTANCE_CM` | `0` (off) | sensor face to bottom of empty crock |
| `CROCK_INTERVAL_SECONDS` | `60` | time between logged readings |
| `CROCK_SAMPLES` | `15` | samples per reading (median is stored) |
| `CROCK_DB_PATH` | `~/crock-level.db` | SQLite file |
| `CROCK_API_URL` | Pioneer API URL | where each reading is POSTed; set to empty to turn off |
| `CROCK_ACCOUNT_NAME` | `mmalish1` | `accountName` sent to the API |

## Looking at the data

```
sqlite3 ~/crock-level.db "SELECT * FROM readings ORDER BY id DESC LIMIT 20;"
```

(`sudo apt install sqlite3` if the command isn't there.)
