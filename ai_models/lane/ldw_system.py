class LaneDepartureWarning:
    def __init__(self, warning_threshold=0.15):
        self.threshold = warning_threshold # Percentage of lane width
        
    def check_departure(self, lanes, frame_width):
        """
        Check if vehicle is departing from lane.
        Assumes camera is mounted in the center of the vehicle.
        """
        left_lane = lanes.get('left_lane')
        right_lane = lanes.get('right_lane')
        
        if left_lane is None or right_lane is None:
            return {'departing': False, 'status': 'unknown'}
            
        # Get x-coordinates at the bottom of the frame (closest to car)
        # Lane format: [[x1, y1], [x2, y2]] where y1 is usually bottom
        left_x = left_lane[0][0]
        right_x = right_lane[0][0]
        
        lane_width = right_x - left_x
        if lane_width <= 0:
            return {'departing': False, 'status': 'error'}
            
        car_center = frame_width / 2
        
        # Calculate distance from center to lanes
        dist_to_left = car_center - left_x
        dist_to_right = right_x - car_center
        
        # Calculate offset ratio (0 = centered, 1 = on line)
        # Ideally car should be at lane_width / 2 from both sides
        ideal_dist = lane_width / 2
        
        # Check left departure
        if dist_to_left < (ideal_dist * self.threshold):
             return {
                'departing': True,
                'direction': 'left',
                'severity': 'warning' if dist_to_left > 0 else 'danger',
                'message': 'Lane Departure Left!'
            }
            
        # Check right departure
        if dist_to_right < (ideal_dist * self.threshold):
            return {
                'departing': True,
                'direction': 'right',
                'severity': 'warning' if dist_to_right > 0 else 'danger',
                'message': 'Lane Departure Right!'
            }
            
        return {'departing': False, 'status': 'centered'}
