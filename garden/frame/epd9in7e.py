"""Minimal driver for the Waveshare 9.7" e-Paper HAT+ (E), Spectra 6, 1120x784.

The init sequence is Waveshare's (waveshareteam/9.7inch_e-Paper_E, epd9in7e.py
at 342301a, MIT licence). The rest is a slimmer version of their
epdconfig.py: spidev + gpiozero only, no ctypes .so files, and a timeout on
the busy pin so a wedged panel can't hang the frame forever.

Pins (BCM): RST 17, DC 25, BUSY 24, PWR 18; SPI0 CE0 (MOSI 10, SCLK 11, CS 8).
"""
from __future__ import annotations

import time

WIDTH, HEIGHT = 1120, 784
RST, DC, BUSY, PWR = 17, 25, 24, 18

INIT = [  # (command, data bytes), from Waveshare's init()
    (0x74, [0x00, 0x0C, 0x0C, 0xD9, 0xDD, 0xDD, 0x15, 0x15, 0x55]),
    (0xF0, [0x49, 0x55, 0x13, 0x5D, 0x05, 0x10]),
    (0xA4, [0x03, 0x00, 0x01, 0x03, 0x00, 0x03, 0x00, 0x00, 0x00]),
    (0x00, [0xDF, 0x6B]),
    (0xA5, [0x44, 0x54, 0x00]),
    (0x30, [0x08]),
    (0x50, [0x37]),
    (0x60, [0x03, 0x03]),
    (0x03, [0x00, 0xC0, 0x03, 0xA8]),
    (0x86, [0x00]),
    (0xE3, [0x22]),
    (0xE0, [0x00]),
    (0x61, [0x04, 0x60, 0x03, 0x10]),
    (0x01, [0x0F, 0x02, 0x28, 0x30, 0x28, 0x42]),
    (0xE7, [0x01]),
    (0xB6, [0x07]),
    (0x06, [0xD0, 0x18]),
    (0xB7, [0x01]),
    (0x05, [0xD0, 0x18]),
    (0xB0, [0x01]),
    (0xB1, [0x02]),
]


class PanelTimeout(RuntimeError):
    pass


class EPD:
    def __init__(self, busy_timeout: float = 90.0):
        import gpiozero
        import spidev

        self.busy_timeout = busy_timeout
        self.rst = gpiozero.LED(RST)
        self.dc = gpiozero.LED(DC)
        self.pwr = gpiozero.LED(PWR)
        self.busy = gpiozero.Button(BUSY, pull_up=False)
        self.spi = spidev.SpiDev()
        self.pwr.on()
        self.spi.open(0, 0)
        self.spi.max_speed_hz = 4_000_000
        self.spi.mode = 0

    def _command(self, cmd: int, data=()) -> None:
        self.dc.off()
        self.spi.writebytes([cmd])
        self.dc.on()
        for b in data:  # one byte per transfer, as Waveshare's driver does for init
            self.spi.writebytes([b])

    def _wait(self, what: str) -> None:
        """BUSY reads 0 while the panel is working."""
        deadline = time.monotonic() + self.busy_timeout
        while not self.busy.value:
            if time.monotonic() > deadline:
                raise PanelTimeout(f"panel still busy after {self.busy_timeout:.0f}s ({what})")
            time.sleep(0.01)
        time.sleep(0.02)

    def _reset(self) -> None:
        for level, ms in ((0, 20), (1, 10), (0, 20), (1, 10)):
            self.rst.value = level
            time.sleep(ms / 1000)

    def init(self) -> None:
        self._reset()
        self._wait("reset")
        for cmd, data in INIT:
            self._command(cmd, data)
        self._command(0x04)  # power on
        self._wait("power on")

    def display(self, buffer: bytes) -> None:
        """buffer: 4 bits per pixel, two pixels per byte (see birddisplay.eink.panel_buffer)."""
        if len(buffer) != WIDTH * HEIGHT // 2:
            raise ValueError(f"buffer is {len(buffer)} bytes, expected {WIDTH * HEIGHT // 2}")
        self.dc.off()
        self.spi.writebytes([0x10])
        self.dc.on()
        self.spi.writebytes2(buffer)
        self._command(0x12, [0x00])  # refresh
        self._wait("refresh")

    def sleep(self) -> None:
        self._command(0x02, [0x01])  # power off
        self._wait("power off")

    def close(self) -> None:
        try:
            self.spi.close()
        finally:
            for pin in (self.rst, self.dc, self.pwr):
                pin.off()
                pin.close()
            self.busy.close()
