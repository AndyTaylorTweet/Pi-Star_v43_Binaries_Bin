#!/usr/bin/env python3

'''
 *   Nextion TFT Uploader
 *   Original: Alex Koren
 *   Python 3 conversion and a full re-write by Andy Taylor (MW0MWZ)
 *   Modified to prefer fast baudrates and always upload at 115200 baud
 *
 *   This program is free software; you can redistribute it and/or modify
 *   it under the terms of the GNU General Public License as published by
 *   the Free Software Foundation; either version 2 of the License, or
 *   (at your option) any later version.
 *
 *   This program is distributed in the hope that it will be useful,
 *   but WITHOUT ANY WARRANTY; without even the implied warranty of
 *   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *   GNU General Public License for more details.
 *
 *   You should have received a copy of the GNU General Public License
 *   along with this program; if not, write to the Free Software
 *   Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
'''

try:
    import serial
except ImportError as e:
    print('\033[31mError: The serial module is missing.\033[0m')
    print('Please install it using: \033[33mapt install python3-serial\033[0m')
    exit(1)
except Exception as e:
    print(f'\033[31mUnexpected error during import: {e}\033[0m')
    exit(1)

import sys
import os
import time
import re
import string

# Try importing serial with error handling
try:
    import serial
except ImportError:
    print('[Error] The serial module is not installed. Please run: apt install python3-serial')
    exit(1)

# ANSI colors
GREEN = '\033[0;32m'
RED = '\033[0;31m'
RESET = '\033[0m'

# Padding helper
LABEL_WIDTH = 18  # a bit extra padding

def clean_string(s):
    """Remove non-printable characters from a string."""
    return ''.join(filter(lambda x: x in string.printable, s))

def print_aligned(label, value, symbol="", color=""):
    space = ' ' * (LABEL_WIDTH - len(label))
    if color:
        print(f"{label}{space}: {color}{value} {symbol}{RESET}")
    else:
        print(f"{label}{space}: {value} {symbol}".rstrip())

def print_trying(speed, success):
    symbol = "✔" if success else "✗"
    color = GREEN if success else RED
    print_aligned(f"Trying {speed}", "", symbol, color)

def print_connected_speed(speed):
    print_aligned("Connected Speed", str(speed), "✔", GREEN)

def print_status(raw_value):
    label = "Status"
    space = ' ' * (LABEL_WIDTH - len(label))

    value = clean_string(raw_value).lower()

    if value == "comok":
        print(f"{label}{space}: {GREEN}comok ✔{RESET}")
    else:
        print(f"{label}{space}: {RED}{value} ⚠{RESET}")

def print_basic(label, value):
    print_aligned(label, value)

def print_success(label, value):
    print_aligned(label, value, "✔", GREEN)

e = b"\xff\xff\xff"

def getBaudrate(ser, fSize=None, checkModel=None):
    for baudrate in [115200, 57600, 38400, 19200, 9600]:
        ser.baudrate = baudrate
        ser.timeout = 3000 / baudrate + .2
        ser.write(e)
        ser.write(b'connect')
        ser.write(e)
        r = ser.read(128)
        success = b'comok' in r
        print_trying(baudrate, success)
        if success:
            parts = r.strip(b"\xff\x00").split(b',')
            status, _, model, fwversion, mcucode, serial_num, flashSize = parts
            status_str = status.split(b' ')[0].decode('utf-8', errors='ignore')
            touchscreen = "yes" if status.split(b' ')[1] == b"1" else "no"
            model_str = model.decode('utf-8', errors='ignore')
            fw = fwversion.decode('utf-8', errors='ignore')
            mcu = mcucode.decode('utf-8', errors='ignore')
            sernum = serial_num.decode('utf-8', errors='ignore')
            flash = flashSize.decode('utf-8', errors='ignore')

            print_connected_speed(baudrate)
            print_status(status_str)
            print_basic("Touchscreen", touchscreen)
            print_success("Model", model_str)
            print_basic("Firmware version", fw)
            print_basic("MCU code", mcu)
            print_basic("Serial", sernum)
            print_basic("Flash size", flash)

            if fSize and fSize > int(flash):
                print(f"{RED}File too big!{RESET}")
                return False
            if checkModel and checkModel.encode() not in model:
                print(f"{RED}Wrong Display!{RESET}")
                return False
            return True
    return False

def setDownloadBaudrate(ser, fSize, baudrate):
    ser.write(b"")
    ser.write(("whmi-wri " + str(fSize) + "," + str(baudrate) + ",0").encode() + e)
    time.sleep(.05)
    ser.baudrate = baudrate
    ser.timeout = .5
    r = ser.read(1)
    if b"\x05" in r:
        print_success("Upload Speed", baudrate)
        return True
    else:
        print_aligned("Upload Speed", str(baudrate), "✗", RED)
    return False

def transferFile(ser, filename, fSize):
    with open(filename, 'rb') as hmif:
        dcount = 0
        while True:
            data = hmif.read(4096)
            if not data:
                break
            dcount += len(data)
            ser.timeout = 5
            ser.write(data)
            sys.stdout.write('\rDownloading, %3.1f%%...' % (dcount / float(fSize) * 100.0))
            sys.stdout.flush()
            ser.timeout = .5
            time.sleep(.5)
            r = ser.read(1)
            if b"\x05" not in r:
                print()
                return False
        print()
    return True

def upload(ser, filename, checkModel=None):
    fSize = os.path.getsize(filename)
    if not getBaudrate(ser, fSize, checkModel):
        print(f"{RED}Could not find baudrate{RESET}")
        exit(1)

    if not setDownloadBaudrate(ser, fSize, 115200):
        print(f"{RED}Could not set upload speed{RESET}")
        exit(1)

    if not transferFile(ser, filename, fSize):
        print(f"{RED}Transfer failed!{RESET}")
        exit(1)

    print(f"{GREEN}File transferred successfully ✔{RESET}")
    exit(0)

if __name__ == "__main__":
    if len(sys.argv) not in [3, 4]:
        print('Usage:\n  python nextion.py file.tft /dev/ttyUSB0 [Model]\nExample:\n  python nextion.py screen.tft /dev/ttyAMA0 NX3224T024')
        exit(1)

    try:
        ser = serial.Serial(sys.argv[2], 9600, timeout=5)
    except serial.serialutil.SerialException:
        print(f"{RED}Could not open serial device {sys.argv[2]}{RESET}")
        exit(1)

    if not ser.is_open:
        ser.open()

    model_check = None
    if len(sys.argv) == 4:
        model_check = sys.argv[3]
        pattern = re.compile("^NX\d{4}[TK]\d{3}$")
        if not pattern.match(model_check):
            print(f"{RED}Invalid model name: {model_check}{RESET}")
            exit(1)

    upload(ser, sys.argv[1], model_check)
