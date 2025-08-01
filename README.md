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
