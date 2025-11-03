# app.py
# Flask web service controlling a 24V LED array via SN74HC595 shift registers
# and ULN2803A Darlington transistor drivers, connected to a Raspberry Pi.

import os
from flask import Flask, request, jsonify
import threading
import time
from flask_cors import CORS
import led_driver as leds  # hardware control layer for SPI communication

STATION_ID = os.getenv("STATION_ID", "unknown").lower()
STATION_LABEL = os.getenv("STATION_LABEL", "Unnamed_Station")
EXPECTED_HOST = f"{STATION_ID}.sorter.sortingfe.dev".lower()

# -----------------------------------------------------------------------------
# Flask app configuration
# -----------------------------------------------------------------------------
app = Flask(__name__, static_folder = "static", static_url_path = "/static")

# Allow API calls from other domains (useful during development)
CORS(app, resources = {r"/api/*" : {"origins" : "*"}})

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
CATEGORY_NAMES = [category.upper() for category in [
    "Misc/Other", "HBA & Household", "Drinks",
    "Pet Supplies", "Snacks & Candy", "Pantry & Breakfast"
]]

STORE_NAMES = [store.upper() for store in [
    "South GR", "Muskegon", "Norton Shores", "Wyoming"
]]

# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------
def normalize_string(input_string: str) -> str:
    """Normalize string formatting for consistent matching."""
    return input_string.strip().upper().replace(" AND ", " & ")


def map_to_led_index(category_name: str, store_name: str) -> int:
    """
    Convert a category and store name into a specific LED index (0–23).
    Each store corresponds to a group of 6 categories (6 LEDs per store).
    """
    normalized_category = normalize_string(category_name)
    normalized_store = normalize_string(store_name)

    # Special case: dedicated backstock LED for South GR
    if normalized_category == "BACKSTOCK" and normalized_store == "SOUTH GR":
        return 24

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

# -----------------------------------------------------------------------------
# API routes for LED control
# -----------------------------------------------------------------------------
@app.post("/api/led/route")
def route_led_request():
    """
    Activate a specific LED based on category/store information.

    Request JSON example:
    {
        "category": "Snacks & Candy",
        "storeName": "South GR",
        "mode": "timed" | "sticky",
        "hold_ms": 10000,
        "dry_run": false
    }
    """
    request_data = request.get_json(force = True)

    # Route validation: check station ID and host
    target_id = (request.data.get("stationId") or "").strip().lower()
    if target_id and target_id != STATION_ID:
        return jsonify(
            ignored = True,
            reason = "station ID mismatch",
            station_id = STATION_ID
        ), 202

    req_host = (request.host or "").split(":")[0].lower()
    if EXPECTED_HOST and req_host and EXPECTED_HOST != req_host:
        return jsonify(
            ignored = True,
            reason = "host mismatch",
            station_id = STATION_ID,
            host = req_host
        ), 202
    
    # Extract parameters from request
    category_name = request_data["category"]
    store_name = request_data["storeName"]
    led_mode = request_data.get("mode", "timed")           # either 'timed' or 'sticky'
    hold_duration_ms = int(request_data.get("hold_ms", 10_000))  # default: 10 seconds
    dry_run_mode = bool(request_data.get("dry_run", False))       # skip hardware if true

    # Determine LED index for this category/store combination
    led_index = map_to_led_index(category_name, store_name)

    # Create one-hot bitmask for SPI write (1 shifted by LED index)
    led_bitmask = (1 << led_index)

    if not dry_run_mode:
        # Send the new bitmask to the LED driver board
        leds.set_mask(led_bitmask)

        # If mode is "timed", schedule a delayed off command
        if led_mode == "timed":
            schedule_all_off(hold_duration_ms)

    # Respond with debug information
    return jsonify(
        ok=True,
        station_id=STATION_ID,
        deviceId=led_index,
        maskHex=f"{led_bitmask:08X}",
        mode=led_mode,
        hold_ms=hold_duration_ms
    )


@app.post("/api/led/off")
def turn_off_all_leds():
    """Immediately turns off all LEDs."""
    leds.all_off()
    return jsonify(ok=True)


@app.get("/api/led/test")
def led_test_sequence():
    """
    Sequentially light each LED one by one to verify wiring and mapping.
    Optional query parameter: ?ms=150 (delay per LED)
    """
    delay_ms = int(request.args.get("ms", "150"))
    for led_index in range(25):  # cycle through LEDs 0–24
        leds.one_hot(led_index)
        time.sleep(delay_ms / 1000.0)
    leds.all_off()
    return jsonify(ok=True)

if __name__ == "__main__":
    # run the dev server on all interfaces so Cloudflare/local can reach it
    app.run(host="0.0.0.0", port=5000, debug=False)

