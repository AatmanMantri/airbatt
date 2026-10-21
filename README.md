# airbatt

One-shot macOS CLI for AirPods left / right / case battery.

```
Aatman’s AirPods Pro
  L  98%
  R  -
  C  -
```

It reads Apple’s Bluetooth stack first (`system_profiler SPBluetoothDataType`), so numbers match Control Center (1% steps). If the AirPods are not listed as connected, it falls back to BLE advertisements (~10% steps, shown as `~85%`).

Missing slots print `-` (closed case, or only one bud in range). Exit `0` if any level is found, `1` otherwise.

## Requirements

- macOS
- Python 3.9+
- Optional: `bleak>=0.22` for BLE fallback (`pip install -r requirements.txt`)

The default macOS path uses only the standard library.

## Install

```bash
git clone https://github.com/AatmanMantri/airbatt.git
cd airbatt
chmod +x airbatt.py
```

BLE fallback (optional):

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Use the venv interpreter **without activating** it:

```bash
.venv/bin/python3 airbatt.py
```

zsh alias (put the clone path in place of `$HOME/path/to/airbatt`):

```zsh
alias airbatt='$HOME/path/to/airbatt/.venv/bin/python3 $HOME/path/to/airbatt/airbatt.py'
```

If you skip the venv, point the alias at `python3` instead. Reload with `source ~/.zshrc`.

## Usage

| Command | When to use it |
| --- | --- |
| `airbatt.py` | Everyday: macOS Bluetooth first, BLE if nothing is connected |
| `airbatt.py --macos` | Only Apple’s 1% numbers; never scan BLE |
| `airbatt.py --ble` | Nearby but not connected; sniff ads (~10% steps) |
| `airbatt.py --json` | Scripts; combine with `--macos` or `--ble` |
| `airbatt.py -h` | Flag reminder |

`--macos` and `--ble` cannot be used together.

```bash
python3 airbatt.py
python3 airbatt.py --json
python3 airbatt.py --macos --json
```

Keep the AirPods nearby. Open the case or wear them so they stay connected or advertise. For BLE, grant **Bluetooth** to Terminal (or iTerm) in System Settings.

---

## minibatt.py (Bluetooth Peripherals Battery)

One-shot CLI to query the battery percentage of connected standard Bluetooth LE peripherals (keyboards, mice, gamepads, etc.) via CoreBluetooth's standard Battery Service (`0x180F`).

### Requirements

```bash
pip install -r requirements.txt
```
*(Requires `pyobjc-framework-CoreBluetooth`)*

### Usage

```bash
# Default (queries "MX Keys Mini"):
python3 minibatt.py

# Query any connected Bluetooth device by name:
python3 minibatt.py "MX Master 3S"
python3 minibatt.py "Magic Keyboard"
```

Output:
```
Connected peripherals seen: ['MX Keys Mini']
MX Keys Mini: 50%
```

If the device is not connected or doesn't expose standard Battery Service, it prints an informative error and exits with code `1`.

## How it works

1. **macOS** — parse `system_profiler SPBluetoothDataType -xml` for `device_batteryLevelLeft` / `Right` / `Case`.
2. **BLE** — scan Apple manufacturer ads (`0x004C`) and decode the nibble battery packet used by AirStatus / zsh-airpods-battery / airpodsgo.

## Credits

Scan and decode ideas from:

- [AirStatus](https://github.com/faglo/AirStatus) (MIT)
- [zsh-airpods-battery](https://github.com/A-delta/zsh-airpods-battery) (MIT)
- [airpodsgo](https://github.com/szerookii/airpodsgo) (MIT)

## License

MIT
