# led_driver.py
import os, threading
try:
    import spidev
except ImportError:
    spidev = None  # allows dry-run on dev hosts

N_LEDS = int(os.getenv("N_LEDS", "25"))
INVERT = bool(int(os.getenv("LED_INVERT", "0")))  # set to 1 if your hardware is inverted

_spi = None
_lock = threading.Lock()

def _open_spi():
    global _spi
    if spidev is None:
        return
    if _spi is None:
        _spi = spidev.SpiDev()
        _spi.open(0, 0)                  # /dev/spidev0.0  (MOSI->SER, SCLK->SRCLK, CE0->RCLK)
        _spi.max_speed_hz = 2_000_000
        _spi.mode = 0

def _to_bytes(mask: int, n_leds: int) -> list[int]:
    """
    Pack a one-hot (or any) mask into bytes for 74HC595 chain.
    We send MSB-first per SPI; adjust byte order so LED0 lives in the LSB of the LAST shifted byte.
    If your chain lights in reverse, flip `buf = buf[::-1]`.
    """
    nbytes = (n_leds + 7) // 8
    buf = []
    for i in range(nbytes):
        buf.insert(0, (mask >> (8 * i)) & 0xFF)  # highest byte first
    return buf

def set_mask(mask: int, n_leds: int = N_LEDS) -> int:
    _open_spi()
    if INVERT:
        mask ^= (1 << n_leds) - 1
    data = _to_bytes(mask, n_leds)
    with _lock:
        if _spi:
            _spi.xfer2(data)  # CE0 (wired to RCLK) latches after transfer
    return mask

def one_hot(index: int, n_leds: int = N_LEDS) -> int:
    if not (0 <= index < n_leds):
        raise ValueError(f"LED index {index} out of range 0..{n_leds-1}")
    return set_mask(1 << index, n_leds)

def all_off():
    return set_mask(0, N_LEDS)
