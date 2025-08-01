from flask import Flask, request, render_template
from led_driver import light_led
from sample_db import UPC_DATABASE, CATEGORIES

app = Flask(__name__)

@app.route('/', methods=['GET', 'POST'])
def index():
    item_name = None
    category = None
    led_index = None
    if request.method == 'POST':
        upc = request.form['upc'].strip()
        record = UPC_DATABASE.get(upc)
        if record:
            item_name, category = record
            led_index = CATEGORIES.index(category)
            light_led(led_index)
        else:
            item_name = "Unknown UPC"
    return render_template('index.html', item_name=item_name, category=category, led_index=led_index)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
