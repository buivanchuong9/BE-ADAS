import cv2
import numpy as np
import logging

logger = logging.getLogger(__name__)

class LaneDetector:
    def __init__(self):
        self.height = 0
        self.width = 0
        self.left_fit = None
        self.right_fit = None
        
        # Perspective transform points (will be initialized based on image size)
        self.src_points = None
        self.dst_points = None
        self.M = None
        self.Minv = None

    def detect_lanes(self, frame):
        """
        Detect lane lines using advanced computer vision techniques:
        1. Perspective Transform (Bird's Eye View)
        2. Color Thresholding (HSL/LAB)
        3. Sliding Window / Polynomial Fitting
        4. Inverse Transform
        """
        try:
            self.height, self.width = frame.shape[:2]
            
            # Initialize perspective transform if needed
            if self.M is None:
                self._init_perspective_transform()
                
            # 1. Undistort (skipped for speed, assuming webcam is decent)
            
            # 2. Thresholding
            binary_warped = self._color_gradient_threshold(frame)
            
            # 3. Perspective Transform
            warped = cv2.warpPerspective(binary_warped, self.M, (self.width, self.height), flags=cv2.INTER_LINEAR)
            
            # 4. Find Lane Pixels & Fit Polynomial
            left_fit, right_fit, lane_data = self._find_lane_pixels(warped)
            
            # Update history (simple smoothing)
            if left_fit is not None:
                self.left_fit = left_fit
            if right_fit is not None:
                self.right_fit = right_fit
                
            # Use history if detection failed
            if left_fit is None: left_fit = self.left_fit
            if right_fit is None: right_fit = self.right_fit
            
            # 5. Calculate curvature and offset (optional, for metadata)
            
            # 6. Draw lanes back onto original image (for visualization/debugging)
            # For the API, we return the polynomial coefficients or points
            
            # Generate points for rendering
            ploty = np.linspace(0, self.height-1, self.height)
            
            left_lane_pts = []
            right_lane_pts = []
            
            if left_fit is not None:
                left_fitx = left_fit[0]*ploty**2 + left_fit[1]*ploty + left_fit[2]
                # Filter points within image bounds
                valid_l = (left_fitx >= 0) & (left_fitx < self.width)
                left_lane_pts = np.column_stack((left_fitx[valid_l], ploty[valid_l])).astype(int).tolist()
                
            if right_fit is not None:
                right_fitx = right_fit[0]*ploty**2 + right_fit[1]*ploty + right_fit[2]
                valid_r = (right_fitx >= 0) & (right_fitx < self.width)
                right_lane_pts = np.column_stack((right_fitx[valid_r], ploty[valid_r])).astype(int).tolist()
            
            # Downsample points for JSON efficiency (every 10th point)
            left_lane_pts = left_lane_pts[::10]
            right_lane_pts = right_lane_pts[::10]
            
            return {
                'left_lane': left_lane_pts,
                'right_lane': right_lane_pts,
                'left_fit': left_fit.tolist() if left_fit is not None else None,
                'right_fit': right_fit.tolist() if right_fit is not None else None
            }
            
        except Exception as e:
            logger.error(f"Error in lane detection: {e}")
            return {'left_lane': [], 'right_lane': []}

    def _init_perspective_transform(self):
        # Define trapezoid for perspective transform
        # Bottom: width of image
        # Top: ~10% of width, centered
        h, w = self.height, self.width
        
        src = np.float32([
            [w * 0.15, h],           # Bottom left
            [w * 0.45, h * 0.6],     # Top left
            [w * 0.55, h * 0.6],     # Top right
            [w * 0.85, h]            # Bottom right
        ])
        
        dst = np.float32([
            [w * 0.2, h],            # Bottom left
            [w * 0.2, 0],            # Top left
            [w * 0.8, 0],            # Top right
            [w * 0.8, h]             # Bottom right
        ])
        
        self.M = cv2.getPerspectiveTransform(src, dst)
        self.Minv = cv2.getPerspectiveTransform(dst, src)

    def _color_gradient_threshold(self, img):
        # Convert to HLS color space
        hls = cv2.cvtColor(img, cv2.COLOR_BGR2HLS)
        s_channel = hls[:,:,2]
        l_channel = hls[:,:,1]
        
        # Threshold S channel (good for yellow/white lines in sun)
        s_thresh_min = 170
        s_thresh_max = 255
        s_binary = np.zeros_like(s_channel)
        s_binary[(s_channel >= s_thresh_min) & (s_channel <= s_thresh_max)] = 1
        
        # Threshold L channel (good for white lines)
        l_thresh_min = 200
        l_thresh_max = 255
        l_binary = np.zeros_like(l_channel)
        l_binary[(l_channel >= l_thresh_min) & (l_channel <= l_thresh_max)] = 1
        
        # Combine
        combined_binary = np.zeros_like(s_binary)
        combined_binary[(s_binary == 1) | (l_binary == 1)] = 1
        
        return combined_binary

    def _find_lane_pixels(self, binary_warped):
        # Histogram
        histogram = np.sum(binary_warped[binary_warped.shape[0]//2:,:], axis=0)
        
        midpoint = np.int64(histogram.shape[0]//2)
        leftx_base = np.argmax(histogram[:midpoint])
        rightx_base = np.argmax(histogram[midpoint:]) + midpoint
        
        # Sliding Window Hyperparameters
        nwindows = 9
        margin = 100
        minpix = 50
        
        window_height = np.int64(binary_warped.shape[0]//nwindows)
        
        nonzero = binary_warped.nonzero()
        nonzeroy = np.array(nonzero[0])
        nonzerox = np.array(nonzero[1])
        
        leftx_current = leftx_base
        rightx_current = rightx_base
        
        left_lane_inds = []
        right_lane_inds = []
        
        for window in range(nwindows):
            win_y_low = binary_warped.shape[0] - (window+1)*window_height
            win_y_high = binary_warped.shape[0] - window*window_height
            
            win_xleft_low = leftx_current - margin
            win_xleft_high = leftx_current + margin
            win_xright_low = rightx_current - margin
            win_xright_high = rightx_current + margin
            
            good_left_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) & 
                            (nonzerox >= win_xleft_low) & (nonzerox < win_xleft_high)).nonzero()[0]
            good_right_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) & 
                            (nonzerox >= win_xright_low) & (nonzerox < win_xright_high)).nonzero()[0]
            
            left_lane_inds.append(good_left_inds)
            right_lane_inds.append(good_right_inds)
            
            if len(good_left_inds) > minpix:
                leftx_current = np.int64(np.mean(nonzerox[good_left_inds]))
            if len(good_right_inds) > minpix:
                rightx_current = np.int64(np.mean(nonzerox[good_right_inds]))
                
        left_lane_inds = np.concatenate(left_lane_inds)
        right_lane_inds = np.concatenate(right_lane_inds)
        
        leftx = nonzerox[left_lane_inds]
        lefty = nonzeroy[left_lane_inds] 
        rightx = nonzerox[right_lane_inds]
        righty = nonzeroy[right_lane_inds]
        
        left_fit = None
        right_fit = None
        
        if len(leftx) > 0:
            left_fit = np.polyfit(lefty, leftx, 2)
        if len(rightx) > 0:
            right_fit = np.polyfit(righty, rightx, 2)
            
        return left_fit, right_fit, None
