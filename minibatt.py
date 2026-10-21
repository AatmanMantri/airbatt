import sys
import time

import CoreBluetooth as CB
import objc
from Foundation import NSDate, NSObject, NSRunLoop

TARGET = sys.argv[1] if len(sys.argv) > 1 else "MX Keys Mini"
BATTERY_SVC = CB.CBUUID.UUIDWithString_("180F")
BATTERY_CHR = CB.CBUUID.UUIDWithString_("2A19")
HID_SVC = CB.CBUUID.UUIDWithString_("1812")


class Delegate(NSObject):
    def init(self):
        self = objc.super(Delegate, self).init()
        self.powered = False
        self.level = None
        self.error = None
        return self

    def centralManagerDidUpdateState_(self, central):
        self.powered = central.state() == CB.CBManagerStatePoweredOn

    def centralManager_didConnectPeripheral_(self, central, peripheral):
        peripheral.setDelegate_(self)
        peripheral.discoverServices_([BATTERY_SVC])

    def centralManager_didFailToConnectPeripheral_error_(self, central, peripheral, error):
        self.error = f"connect failed: {error}"

    def peripheral_didDiscoverServices_(self, peripheral, error):
        if error:
            self.error = f"service discovery failed: {error}"
            return
        for svc in peripheral.services() or []:
            if svc.UUID().isEqual_(BATTERY_SVC):
                peripheral.discoverCharacteristics_forService_([BATTERY_CHR], svc)
                return
        self.error = "device has no battery service"

    def peripheral_didDiscoverCharacteristicsForService_error_(self, peripheral, service, error):
        if error:
            self.error = f"characteristic discovery failed: {error}"
            return
        for ch in service.characteristics() or []:
            if ch.UUID().isEqual_(BATTERY_CHR):
                peripheral.readValueForCharacteristic_(ch)
                return
        self.error = "no battery level characteristic"

    def peripheral_didUpdateValueForCharacteristic_error_(self, peripheral, characteristic, error):
        if error:
            self.error = f"read failed: {error}"
            return
        self.level = bytes(characteristic.value())[0]


def spin(cond, timeout):
    end = time.time() + timeout
    while not cond() and time.time() < end:
        NSRunLoop.currentRunLoop().runUntilDate_(
            NSDate.dateWithTimeIntervalSinceNow_(0.1)
        )


d = Delegate.alloc().init()
mgr = CB.CBCentralManager.alloc().initWithDelegate_queue_(d, None)

spin(lambda: d.powered, 5)
if not d.powered:
    print("Bluetooth not powered on, or permission denied to this terminal.")
    sys.exit(1)

peripherals = list(mgr.retrieveConnectedPeripheralsWithServices_([BATTERY_SVC, HID_SVC]))
print("Connected peripherals seen:", [str(p.name()) for p in peripherals])

target = next((p for p in peripherals if p.name() and TARGET in p.name()), None)
if target is None:
    print(f"{TARGET}: not among connected peripherals")
    sys.exit(1)

mgr.connectPeripheral_options_(target, None)
spin(lambda: d.level is not None or d.error, 10)

if d.level is not None:
    print(f"{TARGET}: {d.level}%")
    sys.exit(0)

print(f"{TARGET}: - ({d.error or 'timed out'})")
sys.exit(1)