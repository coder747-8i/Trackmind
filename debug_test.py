import traceback
import sys

print("Step 1: importing cv2...")
import cv2
print("OK")

print("Step 2: importing mediapipe...")
import mediapipe as mp
print("OK")

print("Step 3: importing numpy...")
import numpy as np
print("OK")

print("Step 4: initializing MediaPipe Pose...")
try:
    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        smooth_landmarks=True,
        min_detection_confidence=0.55,
        min_tracking_confidence=0.5,
    )
    print("OK")
    pose.close()
except Exception as e:
    print(f"FAILED: {e}")
    traceback.print_exc()

print("Step 5: reading one RTSP frame...")
try:
    import os
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay"
    cap = cv2.VideoCapture("rtsp://admin:admin@192.168.1.10/2", cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    ret, frame = cap.read()
    if ret and frame is not None:
        print(f"OK - got frame {frame.shape}")
    else:
        print("FAILED - cap.read() returned no frame")
    cap.release()
except Exception as e:
    print(f"FAILED: {e}")
    traceback.print_exc()

print("\nAll steps done.")
input("Press Enter to exit...")
