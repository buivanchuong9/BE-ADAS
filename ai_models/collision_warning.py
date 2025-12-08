import numpy as np
import time

class CollisionWarningSystem:
    def __init__(self, width=1280, height=720, fps=30):
        self.width = width
        self.height = height
        self.fps = fps
        
        # Camera parameters (approximate for demo)
        # Focal length in pixels. For a standard 60deg FOV camera: F = width / (2 * tan(FOV/2))
        # F ~ 1280 / (2 * tan(30)) ~ 1100
        self.focal_length = 1100 
        
        # Real world dimensions (meters)
        self.AVG_CAR_WIDTH = 1.8
        self.AVG_CAR_HEIGHT = 1.5
        
        # Warning thresholds
        self.TTC_THRESHOLD_CRITICAL = 2.5  # seconds
        self.TTC_THRESHOLD_WARNING = 4.0   # seconds
        
        # Blind spot zones (defined as percentage of screen)
        # Left blind spot: x < 0.3 * width, y > 0.5 * height
        # Right blind spot: x > 0.7 * width, y > 0.5 * height
        self.bsm_zone_y_start = 0.5 * height
        self.bsm_zone_x_left_end = 0.3 * width
        self.bsm_zone_x_right_start = 0.7 * width

    def process(self, tracks, lanes):
        """
        Process tracks and return alerts.
        tracks: List of STrack objects (from ByteTrack)
        lanes: Dict of lane lines
        """
        alerts = []
        
        for track in tracks:
            # 1. Calculate Distance
            distance = self._calculate_distance(track)
            
            # 2. Calculate Relative Speed
            # Kalman filter state: (x, y, a, h, vx, vy, va, vh)
            # vy is vertical velocity in pixels per frame
            # We care mostly about approaching speed (positive vy means moving down/closer if camera is static)
            # But usually for ADAS, objects moving AWAY (vy < 0) or TOWARDS (vy > 0)
            # If we are moving, stationary objects move towards us (vy > 0)
            
            # Let's assume vy is pixels/frame.
            # speed_mps = (vy * fps) * (meters_per_pixel)
            # meters_per_pixel at this distance = Real_Height / Image_Height
            
            bbox = track.tlwh
            h = bbox[3]
            vy = track.mean[5] # velocity y from Kalman Filter
            
            meters_per_pixel = self.AVG_CAR_HEIGHT / h if h > 0 else 0
            relative_speed_mps = (vy * self.fps) * meters_per_pixel
            
            # 3. Calculate TTC
            # TTC = Distance / Relative_Speed
            # If relative_speed > 0 (object getting closer), TTC is positive.
            ttc = float('inf')
            if relative_speed_mps > 0.1: # Threshold to avoid division by zero or noise
                ttc = distance / relative_speed_mps
            
            # 4. Check for FCW (Forward Collision Warning)
            # Only consider objects in the center lane (roughly)
            # Center zone: 0.3 * width < x < 0.7 * width
            cx = bbox[0] + bbox[2]/2
            if 0.25 * self.width < cx < 0.75 * self.width:
                if 0 < ttc < self.TTC_THRESHOLD_CRITICAL:
                    alerts.append({
                        "type": "FCW",
                        "level": "CRITICAL",
                        "message": "COLLISION IMMINENT",
                        "ttc": round(ttc, 1),
                        "track_id": track.track_id,
                        "distance": round(distance, 1)
                    })
                elif 0 < ttc < self.TTC_THRESHOLD_WARNING:
                    alerts.append({
                        "type": "FCW",
                        "level": "WARNING",
                        "message": "Unsafe Distance",
                        "ttc": round(ttc, 1),
                        "track_id": track.track_id,
                        "distance": round(distance, 1)
                    })
            
            # 5. Check for BSM (Blind Spot Monitoring)
            cy = bbox[1] + bbox[3]/2
            if cy > self.bsm_zone_y_start:
                if cx < self.bsm_zone_x_left_end:
                    alerts.append({
                        "type": "BSM",
                        "side": "LEFT",
                        "level": "WARNING",
                        "message": "Vehicle on Left",
                        "track_id": track.track_id
                    })
                elif cx > self.bsm_zone_x_right_start:
                    alerts.append({
                        "type": "BSM",
                        "side": "RIGHT",
                        "level": "WARNING",
                        "message": "Vehicle on Right",
                        "track_id": track.track_id
                    })
                    
            # Attach computed data to track for visualization
            track.distance = distance
            track.ttc = ttc
            track.relative_speed = relative_speed_mps
            
        return alerts

    def _calculate_distance(self, track):
        """
        Estimate distance to object using pinhole camera model.
        D = (F * H_real) / H_image
        """
        bbox = track.tlwh
        h_image = bbox[3]
        
        if h_image <= 0:
            return float('inf')
            
        distance = (self.focal_length * self.AVG_CAR_HEIGHT) / h_image
        return distance
