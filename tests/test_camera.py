import sys
import os
from common import result, load_config, ROOT

def test_camera():
    cfg = load_config()
    cam_index = int(cfg.get("camera_index", 0))

    try:
        import cv2
    except ImportError:
        return result("OpenCV installed", False, "pip install opencv-python")

    cam_index = int(cfg.get("camera_index", 0))
    try:
        cam = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
        if not cam.isOpened():
            cam = cv2.VideoCapture(cam_index)
        if not cam.isOpened():
            return result(f"Webcam opens (index {cam_index})", False, "Camera not accessible")
        ret, frame = cam.read()
        cam.release()
        if not ret:
            return result("Webcam frame captured", False, "read() returned False")
        out = os.path.join(os.path.dirname(__file__), "camera_test.jpg")
        cv2.imwrite(out, frame)
        return result("Webcam frame captured", True, f"saved {out}")
    except Exception as e:
        return result("Webcam capture", False, str(e))

if __name__ == "__main__":
    sys.exit(0 if test_camera() else 1)