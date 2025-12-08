"""
Simple test runner: capture webcam, run local detection (no HTTP),
and display annotated frames to verify performance.

Usage:
  python vision/test_runner.py
"""

import cv2
from vision.detector import run_detection
from vision.lane import detect_lanes


def draw_boxes(image, detections):
    for det in detections:
        x1, y1, x2, y2 = map(int, det["bbox"])
        label = det["label"]
        conf = det["confidence"]
        cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(
            image,
            f"{label}:{conf:.2f}",
            (x1, max(0, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )


def draw_lanes(image, lanes):
    for lane in lanes.get("lanes", []):
        cv2.line(
            image,
            (lane["x1"], lane["y1"]),
            (lane["x2"], lane["y2"]),
            (255, 0, 0),
            2,
        )


def main():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Cannot open webcam")
        return

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            detections, elapsed = run_detection(frame)
            lanes = detect_lanes(frame)

            draw_boxes(frame, detections)
            draw_lanes(frame, lanes)
            cv2.putText(
                frame,
                f"Detections: {len(detections)} | Lanes: {lanes.get('count',0)} | {elapsed*1000:.1f} ms",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("ADAS Vision Test", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()

