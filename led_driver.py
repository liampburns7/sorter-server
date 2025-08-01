import spidev
import gpiod

# Use a confirmed free GPIO — e.g., GPIO5 (BCM5)
CHIP = gpiod.Chip('gpiochip0')
LINE = CHIP.get_line(27)
LINE.request(consumer='led_latch', type=gpiod.LINE_REQ_DIR_OUT, default_vals=[0])

# SPI setup
spi = spidev.SpiDev()
spi.open(0, 0)
spi.max_speed_hz = 1000000

def light_led(index):
    bits = [0] * 24
    if 0 <= index < 24:
        bits[index] = 1

    byte_data = []
    for i in range(0, 24, 8):
        b = 0
        for bit in bits[i:i+8]:
            b = (b << 1) | bit
        byte_data.insert(0, b)

    LINE.set_value(0)
    spi.xfer2(byte_data)
    LINE.set_value(1)

def clear_leds():
    light_led(-1)
