import numpy as np

class LaneTracker:
    def __init__(self, smoothing_factor=0.7):
        self.prev_left = None
        self.prev_right = None
        self.smoothing_factor = smoothing_factor # Higher = more smoothing (slower response)

    def smooth_lanes(self, current_lanes):
        """
        Apply temporal smoothing to reduce jitter in lane detection.
        """
        left_lane = current_lanes.get('left_lane')
        right_lane = current_lanes.get('right_lane')
        
        smoothed_left = self._smooth_line(self.prev_left, left_lane)
        smoothed_right = self._smooth_line(self.prev_right, right_lane)
        
        self.prev_left = smoothed_left
        self.prev_right = smoothed_right
        
        return {
            'left_lane': smoothed_left,
            'right_lane': smoothed_right
        }

    def _smooth_line(self, prev_line, curr_line):
        if curr_line is None:
            return prev_line # Keep previous if current is lost
            
        if prev_line is None:
            return curr_line # Initialize if no previous
            
        # Exponential Moving Average
        # curr_line is [[x1, y1], [x2, y2]]
        
        prev_p1 = np.array(prev_line[0])
        prev_p2 = np.array(prev_line[1])
        
        curr_p1 = np.array(curr_line[0])
        curr_p2 = np.array(curr_line[1])
        
        # Smooth points
        smooth_p1 = prev_p1 * self.smoothing_factor + curr_p1 * (1 - self.smoothing_factor)
        smooth_p2 = prev_p2 * self.smoothing_factor + curr_p2 * (1 - self.smoothing_factor)
        
        return [
            [int(smooth_p1[0]), int(smooth_p1[1])],
            [int(smooth_p2[0]), int(smooth_p2[1])]
        ]
