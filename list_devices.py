#!/usr/bin/env python3
"""
list_devices.py
Lists all available video capture devices on Windows (DirectShow).
Run this if you're not sure what --capture-index to use.
"""
import sys
try:
    import cv2
except ImportError:
    sys.exit("Run INSTALL.bat first to install packages.")

print("Scanning for video capture devices...\n")
found = []
for i in range(10):
    cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
    if cap.isOpened():
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f"  Index {i}: OK  ({w}x{h})")
        found.append(i)
        cap.release()
    else:
        cap.release()

if not found:
    print("  No devices found.")
else:
    print(f"\nUse --capture-index <number> in START_TRACKER.bat")
    print(f"Your capture card is likely the highest index shown above.")

input("\nPress Enter to exit...")
