"""Pick the firmware build target board: detect a connected board by USB ID, else
offer the full supported-board menu.

Devageware never talks to hardware (it compiles in a container), but binding the
build to the board you actually have plugged in keeps the build target and the
later Crucible flash/test on the same device. Detection identifies native-USB
Arduinos by VID/PID; bridge-based boards (ESP32, FTDI/CH340 clones) can't be told
apart by USB ID, so those fall back to the menu.

list_ports.comports() also returns motherboard ttyS* placeholders (no USB VID);
we keep only real USB devices (vid is not None).
"""

from dataclasses import dataclass

import serial.tools.list_ports as list_ports


@dataclass(frozen=True)
class Board:
    display: str       # human label, e.g. "Arduino Nano Every"
    board: str         # PlatformIO/Zephyr board id, e.g. "nano_every"
    platform: str      # PlatformIO platform / Zephyr family, e.g. "atmelmegaavr"
    vendor: str        # "Arduino" | "Nordic" | "NXP"
    mcu: str           # e.g. "ATmega4809"
    toolchain: str     # "platformio" | "ncs" | "zephyr"
    framework: str     # "arduino" | "zephyr"
    language: str      # "cpp" | "c"


# Boards Devageware can build for (notes § Devageware "Supported Platforms").
SUPPORTED_BOARDS: list[Board] = [
    Board("Arduino Nano Every", "nano_every", "atmelmegaavr", "Arduino", "ATmega4809", "platformio", "arduino", "cpp"),
    Board("Arduino Nano (classic)", "nanoatmega328", "atmelavr", "Arduino", "ATmega328P", "platformio", "arduino", "cpp"),
    Board("Arduino Uno", "uno", "atmelavr", "Arduino", "ATmega328P", "platformio", "arduino", "cpp"),
    Board("Arduino Mega 2560", "megaatmega2560", "atmelavr", "Arduino", "ATmega2560", "platformio", "arduino", "cpp"),
    Board("ESP32 DevKit", "esp32dev", "espressif32", "Espressif", "ESP32", "platformio", "arduino", "cpp"),
    Board("ESP32-S3 DevKitC-1", "esp32-s3-devkitc-1", "espressif32", "Espressif", "ESP32-S3", "platformio", "arduino", "cpp"),
    Board("Nordic nRF54L15 DK", "nrf54l15dk", "nrf54l15", "Nordic", "nRF54L15", "ncs", "zephyr", "c"),
    Board("NXP i.MXRT1062 EVK", "mimxrt1062_evk", "mimxrt1062", "NXP", "i.MXRT1062", "zephyr", "zephyr", "c"),
]

_BY_BOARD_ID = {b.board: b for b in SUPPORTED_BOARDS}

# USB (vid, pid) -> board id, only for boards we can positively identify.
VIDPID_TO_BOARD = {
    (0x2341, 0x0058): "nano_every",
    (0x2341, 0x0043): "uno",
    (0x2341, 0x0001): "uno",
    (0x2A03, 0x0043): "uno",
    (0x2341, 0x0042): "megaatmega2560",
    (0x2341, 0x0010): "megaatmega2560",
    (0x2A03, 0x0042): "megaatmega2560",
}


@dataclass
class Detected:
    device: str
    vidpid: tuple[int, int] | None
    description: str | None
    serial_number: str | None
    board: Board | None  # matched supported board, or None if unidentified


def detect_connected() -> list[Detected]:
    """USB serial devices currently connected, with a matched Board when the USB
    ID is recognised."""
    out: list[Detected] = []
    for p in list_ports.comports():
        if p.vid is None:
            continue
        vidpid = (p.vid, p.pid)
        board = _BY_BOARD_ID.get(VIDPID_TO_BOARD.get(vidpid, ""))
        out.append(Detected(p.device, vidpid, p.description, p.serial_number, board))
    return sorted(out, key=lambda d: d.device)


def _vp(vidpid: tuple[int, int] | None) -> str:
    return f"{vidpid[0]:04x}:{vidpid[1]:04x}" if vidpid else "????:????"


def select_board() -> Board | None:
    """Interactively choose the build-target board.

    Offers positively-identified connected boards first, then the full supported
    menu. Returns the chosen Board, or None if the engineer skips (LLM decides
    the platform from the spec, as before).
    """
    detected = detect_connected()
    identified = [d for d in detected if d.board is not None]
    unidentified = [d for d in detected if d.board is None]

    print("\n🎯 Build target board")
    if detected:
        print("   Connected USB devices:")
        for d in detected:
            tag = d.board.display if d.board else f"{d.description or 'unidentified'} (not auto-matched)"
            print(f"     • {tag}  [{_vp(d.vidpid)}]  → {d.device}")
    else:
        print("   (no USB devices detected)")

    options: list[tuple[str, Board]] = []
    for d in identified:
        options.append((f"{d.board.display}  — detected on {d.device}", d.board))

    print("\n   Select the build target:")
    idx = 0
    for label, _ in options:
        idx += 1
        print(f"     [{idx}] {label}")
    menu_start = idx
    for b in SUPPORTED_BOARDS:
        idx += 1
        print(f"     [{idx}] {b.display}  ({b.board} / {b.vendor})")
    print(f"     [0] Skip — let the requirements/LLM decide")

    while True:
        choice = input("   Board (number): ").strip()
        if not choice.isdigit():
            print("   Invalid selection.")
            continue
        n = int(choice)
        if n == 0:
            return None
        if 1 <= n <= menu_start:
            return options[n - 1][1]
        if menu_start < n <= idx:
            return SUPPORTED_BOARDS[n - menu_start - 1]
        print("   Invalid selection.")
