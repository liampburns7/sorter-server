# app.py
from flask import Flask, request, jsonify, url_for
import threading, time
from flask_cors import CORS
import led_driver as leds

app = Flask(__name__, static_folder = "static", static_url_path="/static")

@app.get("/health")
def health():
	return jsonify(status="ok"), 200

@app.get("/test")
def test_page():
	return app.send_static_file("led_tester.html")

@app.get("/_routes")
def _routes():
	return jsonify(sorted([f"{sorted(r.methods)} {r.rule}" for r in app.url_map.iter_rules()]))

CORS(app, resources={r"/api/*": {"origins": "*"}})  # permissive; fine for quick testing

CATEGORIES = [c.upper() for c in [
    "Misc/Other","HBA & Household","Drinks","Pet Supplies","Snacks & Candy","Pantry & Breakfast"
]]
STORES = [s.upper() for s in ["SOUTH GR","MUSKEGON","NORTON SHORES","WYOMING"]]

def _norm(s: str) -> str:
    return s.strip().upper().replace(" AND ", " & ")

def _to_device_id(category: str, store: str) -> int:
    cu, su = _norm(category), _norm(store)
    if cu == "BACKSTOCK" and su == "SOUTH GR":
        return 24
    try:
        return STORES.index(su) * len(CATEGORIES) + CATEGORIES.index(cu)
    except ValueError as e:
        raise ValueError(f"Unknown store/category: store={store}, category={category}") from e

def _off_in(ms):
    def _t():
        time.sleep(ms / 1000.0)
        leds.all_off()
    threading.Thread(target=_t, daemon=True).start()

@app.post("/api/led/route")
def led_route():
    j = request.get_json(force=True)
    category = j["category"]
    store = j["storeName"]
    mode = j.get("mode", "timed")      # "timed" | "sticky"
    hold_ms = int(j.get("hold_ms", 10_000))
    dry = bool(j.get("dry_run", False))

    dev = _to_device_id(category, store)
    mask = (1 << dev)

    if not dry:
        leds.set_mask(mask)            # one-hot → clears all other LEDs
        if mode == "timed":
            _off_in(hold_ms)

    return jsonify(ok=True, deviceId=dev, maskHex=f"{mask:08X}", mode=mode, hold_ms=hold_ms)

@app.post("/api/led/off")
def led_off():
    leds.all_off()
    return jsonify(ok=True)

@app.get("/api/led/test")
def led_test():
    ms = int(request.args.get("ms", "150"))
    for i in range(25):
        leds.one_hot(i)
        time.sleep(ms / 1000.0)
    leds.all_off()
    return jsonify(ok=True)
