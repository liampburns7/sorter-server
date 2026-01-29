# app.py
# Flask web service controlling a 24V LED array via SN74HC595 shift registers
# and ULN2803A Darlington transistor drivers, connected to a Raspberry Pi.

import os
from flask import Flask, request, jsonify
import threading
import time
from flask_cors import CORS
import led_driver as leds  # hardware control layer for SPI communication
from dotenv import load_dotenv

load_dotenv()

STATION_ID = os.getenv("STATION_ID", "unknown").lower()
STATION_LABEL = os.getenv("STATION_LABEL", "Unnamed_Station")

# -----------------------------------------------------------------------------
# LED mapping constants
# -----------------------------------------------------------------------------

# Special function LEDs
WAREHOUSE_LED_MAP = {
    "ADD TO QTY": 8,
    "UNIQUES": 9,
    "BACKSTOCK": 10
}

# Categories the API is allowed to receive from Korting/front-end
API_CATEGORY_NAMES = {
    "MISC/OTHER",
    "HBA & HOUSEHOLD",
    "DRINKS",
    "PET SUPPLIES",
    "SNACKS & CANDY",
    "PANTRY & BREAKFAST",
}

# Collapse API categories down to hardware categories
API_TO_HARDWARE_CATEGORY = {
    "HBA & HOUSEHOLD": "CHEMICAL",
}


# -----------------------------------------------------------------------------
# Flask app configuration
# -----------------------------------------------------------------------------
app = Flask(__name__, static_folder = "static", static_url_path = "/static")

# Allow API calls from an allowlist of origins (configurable via environment)
CORS(app, resources={r"/*": {"origins": "*"}})

# -------------------------------------------------------------------------
# Blink controller (non-blocking, retriggers even for same LED)
# -------------------------------------------------------------------------
_blink_lock = threading.Lock()
_blink_cancel = None
_blink_job_id = 0

# -----------------------------------------------------------------------------
# Basic diagnostic endpoints
# -----------------------------------------------------------------------------
@app.get("/health")
def health_check():
    """Basic health check endpoint."""
    return jsonify(status = "ok", station_id = STATION_ID, station_label = STATION_LABEL), 200


@app.get("/test")
def static_test_page():
    """Serves the local LED tester HTML page."""
    return app.send_static_file("led_tester.html")


@app.get("/_routes")
def list_routes():
    """Debug utility: returns a list of available routes."""
    route_list = [f"{sorted(route.methods)} {route.rule}" for route in app.url_map.iter_rules()]
    return jsonify(sorted(route_list))

# -----------------------------------------------------------------------------
# Constants for store/category mapping
# -----------------------------------------------------------------------------

# Hardware categories (the only ones that map to LEDs per store)
CATEGORY_NAMES = [category.upper() for category in [
    "Grocery", "Chemical"
]]


STORE_NAMES = [store.upper() for store in [
    "Muskegon", "Norton Shores", "South GR", "Wyoming"
]]

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
def normalize_string(input_string: str) -> str:
    """Normalize string formatting for consistent matching."""
    return input_string.strip().upper().replace(" AND ", " & ")

def collapse_category(category_name: str, store_name: str) -> str:
    """
    Converts API-level categories into hardware-level categories.
    Special warehouse categories are NOT collapsed (ADD TO QTY, UNIQUES).
    """
    normalized_category = normalize_string(category_name)
    normalized_store = normalize_string(store_name)

    # If this is a warehouse/special call, do NOT collapse
    if normalized_store == "WAREHOUSE":
        return normalized_category

    # Validate incoming API category names (optional but recommended)
    if normalized_category not in API_CATEGORY_NAMES:
        raise ValueError(f"Unknown API category={category_name}")

    # Enforce category/store constraints
    if normalized_category == "BACKSTOCK" and normalized_store != "WAREHOUSE":
        raise ValueError("BACKSTOCK is only valid for storeName='Warehouse'")

    # Map down to hardware categories
    return API_TO_HARDWARE_CATEGORY.get(normalized_category, "GROCERY")


def map_to_led_index(category_name: str, store_name: str) -> int:
    """
    Convert category + store into an LED index.
    Grid LEDs: 0..(len(STORE_NAMES)*len(CATEGORY_NAMES)-1)
    Special LEDs: storeName == "WAREHOUSE" uses WAREHOUSE_LED_MAP
    """
    normalized_category = normalize_string(category_name)
    normalized_store = normalize_string(store_name)
    
    # Special case: dedicated add to qty LED
    if normalized_store == "WAREHOUSE":
        try:
            return WAREHOUSE_LED_MAP[normalized_category]
        except KeyError as error:
            raise ValueError(
                f"Unknown WAREHOUSE category={category_name}"
            ) from error

    try:
        # Flatten store/category grid: LED index = store_index * num_categories + category_index
        store_index = STORE_NAMES.index(normalized_store)
        category_index = CATEGORY_NAMES.index(normalized_category)
        return store_index * len(CATEGORY_NAMES) + category_index
    except ValueError as error:
        raise ValueError(
            f"Unknown store/category combination: store={store_name}, category={category_name}"
        ) from error


def schedule_all_off(delay_ms: int):
    """Turn all LEDs off after a given delay (runs asynchronously)."""
    def delayed_off_task():
        time.sleep(delay_ms / 1000.0)
        leds.all_off()
    threading.Thread(target=delayed_off_task, daemon=True).start()

def blink_then_hold(mask: int, hz: float = 2.0, blink_s: float = 2.0):
    """
    Blink `mask` at `hz` for `blink_s` seconds, then leave it ON steady.
    Retriggering cancels any in-progress blink immediately.
    """
    global _blink_cancel, _blink_job_id

    with _blink_lock:
        _blink_job_id += 1
        my_job = _blink_job_id

        # cancel the previous blink if it exists
        if _blink_cancel is not None:
            _blink_cancel.set()

        _blink_cancel = threading.Event()
        cancel_evt = _blink_cancel

    def _worker():
        period = 1.0 / hz
        half = period / 2.0
        t_end = time.time() + blink_s
        on = True

        # blink loop
        while time.time() < t_end:
            if cancel_evt.is_set():
                return  # killed by a newer request

            leds.set_mask(mask if on else 0)
            on = not on
            time.sleep(half)

        # if we finished normally and we're still the latest job, leave LED ON
        with _blink_lock:
            if cancel_evt.is_set() or my_job != _blink_job_id:
                return
        leds.set_mask(mask)

    threading.Thread(target=_worker, daemon=True).start()

# -----------------------------------------------------------------------------
# API routes for LED control
# -----------------------------------------------------------------------------
@app.post("/api/led/route")
def route_led_request():
    """
    Activate a specific LED based on category/store information.

    Request JSON example:
    {
        "stationId": "sorter1",
        "category": "Snacks & Candy",
        "storeName": "South GR",
        "mode": "timed" | "sticky",
        "hold_ms": 10000,
        "dry_run": false
    }
    """
    request_data = request.get_json(force = True)

    # Route validation: check station ID and host
    target_id = (request_data.get("stationId") or "").strip().lower()
    if target_id and target_id != STATION_ID:
        return jsonify(
            ignored = True,
            reason = "station ID mismatch",
            station_id = STATION_ID
        ), 202
    
    # Extract parameters from request
    category_name = request_data.get("category")
    store_name = request_data.get("storeName")
    if not category_name or not store_name:
        return jsonify(ok=False, error="Missing category or storeName"), 400
    led_mode = request_data.get("mode", "timed")           # either 'timed' or 'sticky'
    hold_duration_ms = int(request_data.get("hold_ms", 10_000))  # default: 10 seconds
    dry_run_mode = bool(request_data.get("dry_run", False))       # skip hardware if true

    # Collapse API category -> hardware category (except warehouse specials)
    try:
        collapsed_category = collapse_category(category_name, store_name)
        led_index = map_to_led_index(collapsed_category, store_name)
    except ValueError as e:
        return jsonify(ok=False, error=str(e)), 400



    # Create one-hot bitmask for SPI write (1 shifted by LED index)
    led_bitmask = (1 << led_index)

    if not dry_run_mode:
        # Blink for 2 seconds at 2 Hz, then stay ON
        blink_then_hold(led_bitmask, hz=2.0, blink_s=2.0)

        # If mode is "timed", schedule a delayed off command
        if led_mode == "timed":
            schedule_all_off(hold_duration_ms)


    # Respond with debug information
    return jsonify(
        ok=True,
        station_id=STATION_ID,
        deviceId=led_index,
        maskHex=hex(led_bitmask),
        mode=led_mode,
        hold_ms=hold_duration_ms,
        category_in=category_name,
        category_mapped=collapsed_category,
        store=store_name
    )



@app.post("/api/led/off")
def turn_off_all_leds():
    """Immediately turns off all LEDs."""
    global _blink_cancel
    with _blink_lock:
        if _blink_cancel is not None:
            _blink_cancel.set()
    leds.all_off()
    return jsonify(ok=True)


@app.get("/api/led/test")
def led_test_sequence():
    """
    Sequentially light each LED one by one to verify wiring and mapping.
    Optional query parameter: ?ms=150 (delay per LED)
    """
    delay_ms = int(request.args.get("ms", "150"))
    for led_index in list(range(len(STORE_NAMES)*len(CATEGORY_NAMES))) + list(WAREHOUSE_LED_MAP.values()):
        leds.one_hot(led_index)
        time.sleep(delay_ms / 1000.0)
    leds.all_off()
    return jsonify(ok=True)

if __name__ == "__main__":
    # run the dev server on all interfaces so Cloudflare/local can reach it
    app.run(host="0.0.0.0", port=5000, debug=False)

