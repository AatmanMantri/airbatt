#!/usr/bin/env python3
"""One-shot AirPods battery: macOS system_profiler, then BLE ads."""

from __future__ import annotations

import argparse
import asyncio
import json
import plistlib
import subprocess
import sys
from binascii import hexlify
from dataclasses import dataclass
from typing import Any, Optional

AIRPODS_MANUFACTURER = 76  # 0x004C Apple
AIRPODS_DATA_LENGTH = 54
APPLE_VENDOR = "0x004c"

BLE_MODELS = {
    "e": "AirPods Pro",
    "3": "AirPods 3",
    "f": "AirPods 2",
    "2": "AirPods 1",
    "a": "AirPods Max",
}


@dataclass
class BatteryReport:
    name: str
    source: str  # macos | ble
    left: Optional[int] = None
    right: Optional[int] = None
    case: Optional[int] = None
    charging_left: Optional[bool] = None
    charging_right: Optional[bool] = None
    charging_case: Optional[bool] = None
    approximate: bool = False

    def has_level(self) -> bool:
        return any(v is not None for v in (self.left, self.right, self.case))

    def to_json(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "name": self.name,
            "left": self.left,
            "right": self.right,
            "case": self.case,
            "charging_left": self.charging_left,
            "charging_right": self.charging_right,
            "charging_case": self.charging_case,
            "approximate": self.approximate,
        }


def parse_percent(value: Any) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip().replace("%", "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _looks_like_airpods(name: str, info: dict[str, Any]) -> bool:
    lowered = name.lower()
    if "airpods" in lowered:
        return True
    vendor = str(info.get("device_vendorID", "")).lower()
    has_battery = any(
        key.startswith("device_batteryLevel") for key in info
    )
    return APPLE_VENDOR in vendor and has_battery


def _report_from_device_info(name: str, info: dict[str, Any]) -> Optional[BatteryReport]:
    if not isinstance(info, dict) or not _looks_like_airpods(name, info):
        return None
    single = parse_percent(info.get("device_batteryLevelSingle"))
    left = parse_percent(info.get("device_batteryLevelLeft"))
    right = parse_percent(info.get("device_batteryLevelRight"))
    case = parse_percent(info.get("device_batteryLevelCase"))
    if single is not None and left is None and right is None:
        left = single
    report = BatteryReport(
        name=name,
        source="macos",
        left=left,
        right=right,
        case=case,
        approximate=False,
    )
    return report if report.has_level() else None


def _walk_connected(node: Any) -> Optional[BatteryReport]:
    if isinstance(node, dict):
        # Format: { "Aatman’s AirPods Pro": { device_batteryLevelLeft: "98%", ... } }
        battery_keys = any(
            isinstance(k, str) and k.startswith("device_batteryLevel") for k in node
        )
        if battery_keys:
            name = str(node.get("device_name") or "AirPods")
            return _report_from_device_info(name, node)
        for key, value in node.items():
            if isinstance(value, dict):
                found = _report_from_device_info(str(key), value)
                if found:
                    return found
            found = _walk_connected(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _walk_connected(item)
            if found:
                return found
    return None


def read_macos() -> Optional[BatteryReport]:
    try:
        raw = subprocess.check_output(
            ["system_profiler", "SPBluetoothDataType", "-xml"],
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    try:
        plist = plistlib.loads(raw)
    except Exception:
        return None
    connected: Any = None
    if isinstance(plist, list):
        for block in plist:
            if not isinstance(block, dict):
                continue
            for item in block.get("_items") or []:
                if isinstance(item, dict) and "device_connected" in item:
                    connected = item["device_connected"]
                    break
    if connected is None:
        return None
    return _walk_connected(connected)


def _nibble_percent(raw: bytes, index: int) -> Optional[int]:
    value = int(chr(raw[index]), 16)
    if value == 10:
        return 100
    if value <= 10:
        return value * 10 + 5
    return None


def decode_ble_hex(raw: bytes) -> Optional[BatteryReport]:
    if len(raw) != AIRPODS_DATA_LENGTH:
        return None
    try:
        if int(chr(raw[1]), 16) != 7:
            return None
    except ValueError:
        return None
    flip = (int(chr(raw[10]), 16) & 0x02) == 0
    left = _nibble_percent(raw, 12 if flip else 13)
    right = _nibble_percent(raw, 13 if flip else 12)
    case = _nibble_percent(raw, 15)
    charging = int(chr(raw[14]), 16)
    charging_left = (charging & (0b00000010 if flip else 0b00000001)) != 0
    charging_right = (charging & (0b00000001 if flip else 0b00000010)) != 0
    charging_case = (charging & 0b00000100) != 0
    model = BLE_MODELS.get(chr(raw[7]), "AirPods")
    report = BatteryReport(
        name=model,
        source="ble",
        left=left,
        right=right,
        case=case,
        charging_left=charging_left if left is not None else None,
        charging_right=charging_right if right is not None else None,
        charging_case=charging_case if case is not None else None,
        approximate=True,
    )
    return report if report.has_level() else None


async def _scan_ble() -> Optional[BatteryReport]:
    from bleak import BleakScanner

    found = await BleakScanner.discover(timeout=5.0, return_adv=True)
    for _device, adv in found.values():
        mfg = adv.manufacturer_data
        if AIRPODS_MANUFACTURER not in mfg:
            continue
        data_hex = hexlify(bytearray(mfg[AIRPODS_MANUFACTURER]))
        decoded = decode_ble_hex(data_hex)
        if decoded:
            return decoded
    return None


def read_ble() -> tuple[Optional[BatteryReport], Optional[str]]:
    try:
        import bleak  # noqa: F401
    except ImportError:
        return None, "BLE fallback skipped: pip install 'bleak>=0.22'"
    try:
        return asyncio.run(_scan_ble()), None
    except Exception as exc:
        return None, f"BLE scan failed: {exc}"


def format_slot(value: Optional[int], approximate: bool, charging: Optional[bool]) -> str:
    if value is None:
        return "-"
    text = f"~{value}%" if approximate else f"{value}%"
    if charging:
        text += " ⚡"
    return text


def format_text(report: BatteryReport) -> str:
    title = report.name
    if report.approximate:
        title += " (~10% steps)"
    lines = [
        title,
        f"  L  {format_slot(report.left, report.approximate, report.charging_left)}",
        f"  R  {format_slot(report.right, report.approximate, report.charging_right)}",
        f"  C  {format_slot(report.case, report.approximate, report.charging_case)}",
    ]
    return "\n".join(lines)


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print AirPods left / right / case battery."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--macos",
        action="store_true",
        help="Only use system_profiler (skip BLE).",
    )
    source.add_argument(
        "--ble",
        action="store_true",
        help="Only scan BLE advertisements (skip system_profiler).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Machine-readable JSON.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    report: Optional[BatteryReport] = None
    hint: Optional[str] = None

    if args.ble:
        report, hint = read_ble()
    else:
        report = read_macos()
        if report is None and not args.macos:
            report, hint = read_ble()

    if report is None:
        if args.json:
            payload = {"status": 0, "error": "AirPods not found"}
            if hint:
                payload["hint"] = hint
            print(json.dumps(payload))
        else:
            print("AirPods not found.")
            if hint:
                print(hint, file=sys.stderr)
        return 1

    if args.json:
        payload = report.to_json()
        payload["status"] = 1
        print(json.dumps(payload))
    else:
        print(format_text(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
