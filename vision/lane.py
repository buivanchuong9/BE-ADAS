import cv2
import numpy as np
from typing import Dict, Any, List


def detect_lanes(image: np.ndarray) -> Dict[str, Any]:
    """
    Simple lane detection using Canny + Hough transform.
    This is lightweight and works as a fallback; replace with LaneNet/UltraFastLane for production.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)

    height, width = edges.shape
    mask = np.zeros_like(edges)
    polygon = np.array([[
        (0, height),
        (width, height),
        (int(0.6 * width), int(0.6 * height)),
        (int(0.4 * width), int(0.6 * height))
    ]], np.int32)
    cv2.fillPoly(mask, polygon, 255)
    masked_edges = cv2.bitwise_and(edges, mask)

    lines = cv2.HoughLinesP(masked_edges, 1, np.pi / 180, threshold=50, minLineLength=40, maxLineGap=100)
    lane_lines: List[Dict[str, Any]] = []
    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            lane_lines.append({"x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2)})

    return {"lanes": lane_lines, "count": len(lane_lines)}

