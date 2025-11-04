# Raspberry Pi LED Sorter

This project runs a Flask web server on a Raspberry Pi to control LEDs via SN74HC595 shift registers and ULN2803A drivers based on scanned UPC input.

## Features
- Sorts items by UPC into 24 categories
- Lights the corresponding LED for each scanned item
- Flask web server with simple HTML interface
- Hardware-ready SPI output

## File Structure
- `app.py` — Flask server, handles form and LED triggering
- `led_driver.py` — SPI interface and LED logic
- `sample_db.py` — Lookup table of 50 pseudo-UPCs
- `templates/index.html` — horrific UI page for entering UPCs

## Deployment Notes
- Create a `.env` file (or otherwise set environment variables) with station-specific
  values:
  - `STATION_ID` — lowercase identifier matching incoming requests.
  - `STATION_LABEL` — human-readable label shown in diagnostics.
  - `ALLOWED_ORIGINS` — comma-separated list of origins that may access the API. If
    omitted, the server defaults to `https://sorter.sortingfe.dev`.
