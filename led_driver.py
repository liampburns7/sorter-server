"""
led_driver.py
-------------
GPIO control helpers for the sorter server.

- Lazy-imports `gpiod` so the Flask app can boot even if GPIO isn't ready.
- Opens the chip by FULL PATH ("/dev/gpiochip0") for modern libgpiod.
- Works with both libgpiod v2 (request_lines API) and v1 (get_line API).
- Cleans up handles every call to avoid leaking resources.

Usage:
    from led_driver import light_led
    light_led(17, True)   # example: set line offset 17 high
"""

from typing import Optional


GPIO_CHIP_PATH = "/dev/gpiochip0"


def _have_gpiod_v2(gpiod_module) -> bool:
    """Detect libgpiod v2-style API."""
    return hasattr(gpiod_module, "LineSettings") and hasattr(gpiod_module, "LineDirection")


def light_led(line_offset: int, state: bool) -> bool:
    """
    Set a single GPIO line to the given boolean state.

    Args:
        line_offset: The *line offset* on gpiochip0 (not BCM pin number).
        state: True for HIGH, False for LOW.

    Returns:
        True on success, False on failure (does not raise for common runtime issues).
    """
    try:
        import gpiod  # Lazy import so the server doesn't die on module import
    except Exception as e:
        # Keep the server alive; log-friendly error message
        print(f"[led_driver] ERROR: failed to import gpiod: {e}")
        return False

    try:
        chip = gpiod.Chip(GPIO_CHIP_PATH)  # Use full device path
    except Exception as e:
        print(f"[led_driver] ERROR: cannot open {GPIO_CHIP_PATH}: {e}")
        return False

    # v2 path (preferred)
    if _have_gpiod_v2(gpiod):
        req = None
        try:
            settings = gpiod.LineSettings(direction=gpiod.LineDirection.OUTPUT)
            # request_lines expects a dict {line_offset: LineSettings}
            req = chip.request_lines(consumer="sorter", config={line_offset: settings})
            # set_values expects a dict {line_offset: value}
            req.set_values({line_offset: 1 if state else 0})
            return True
        except Exception as e:
            print(f"[led_driver] ERROR (v2): {e}")
            return False
        finally:
            try:
                if req is not None:
                    req.release()
            except Exception:
                pass
            try:
                chip.close()
            except Exception:
                pass

    # v1 fallback
    try:
        line = chip.get_line(line_offset)
        line.request(consumer="sorter", type=gpiod.LINE_REQ_DIR_OUT, default_vals=[1 if state else 0])
        line.set_value(1 if state else 0)
        return True
    except Exception as e:
        print(f"[led_driver] ERROR (v1): {e}")
        return False
    finally:
        try:
            # v1 API: release the line handle
            line.release()  # type: ignore[name-defined]
        except Exception:
            pass
        try:
            chip.close()
        except Exception:
            pass


def pulse_led(line_offset: int, ms: int = 200) -> bool:
    """
    Convenience helper: briefly drive a line HIGH then LOW.

    Args:
        line_offset: GPIO line offset.
        ms: Pulse width in milliseconds.
    """
    import time
    if not light_led(line_offset, True):
        return False
    time.sleep(ms / 1000.0)
    return light_led(line_offset, False)

