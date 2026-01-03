"""
Kalman Filter for Lane Tracking
=================================
Simple Kalman Filter implementation for smoothing lane coefficients.

Author: Senior ADAS Engineer
Date: 2026-01-03
"""

import numpy as np
from typing import Optional, Tuple


class KalmanFilter:
    """
    1D Kalman Filter for scalar value smoothing.
    Used for smoothing each coefficient of lane polynomial.
    """
    
    def __init__(
        self,
        process_variance: float = 0.01,
        measurement_variance: float = 0.1,
        initial_estimate: Optional[float] = None
    ):
        """
        Initialize Kalman Filter.
        
        Args:
            process_variance: How much we expect the value to change (Q)
            measurement_variance: Measurement noise variance (R)
            initial_estimate: Initial state estimate
        """
        self.process_variance = process_variance  # Q
        self.measurement_variance = measurement_variance  # R
        
        # State
        self.estimate = initial_estimate  # Current estimate
        self.estimate_error = 1.0  # Initial error covariance (P)
    
    def update(self, measurement: float, confidence: float = 1.0) -> float:
        """
        Update filter with new measurement.
        
        Args:
            measurement: New measured value
            confidence: Measurement confidence [0-1], scales measurement variance
            
        Returns:
            Filtered value
        """
        # Initialize on first measurement
        if self.estimate is None:
            self.estimate = measurement
            return self.estimate
        
        # Prediction step
        # x_pred = x_prev (no process model, assuming constant value)
        # P_pred = P_prev + Q
        prediction_error = self.estimate_error + self.process_variance
        
        # Update step
        # K = P_pred / (P_pred + R)
        # Adjust measurement variance by confidence
        adjusted_R = self.measurement_variance / max(confidence, 0.1)
        kalman_gain = prediction_error / (prediction_error + adjusted_R)
        
        # x_new = x_pred + K * (z - x_pred)
        self.estimate = self.estimate + kalman_gain * (measurement - self.estimate)
        
        # P_new = (1 - K) * P_pred
        self.estimate_error = (1 - kalman_gain) * prediction_error
        
        return self.estimate
    
    def reset(self):
        """Reset filter state."""
        self.estimate = None
        self.estimate_error = 1.0


class LaneKalmanFilter:
    """
    Kalman Filter for lane polynomial coefficients.
    Smooths 2nd order polynomial: y = a*x^2 + b*x + c
    """
    
    def __init__(
        self,
        process_variance: float = 0.01,
        measurement_variance: float = 0.1
    ):
        """
        Initialize lane Kalman Filter.
        
        Args:
            process_variance: Process noise (how much lane can change)
            measurement_variance: Measurement noise (detection uncertainty)
        """
        # Separate filter for each coefficient
        self.filter_a = KalmanFilter(process_variance, measurement_variance)
        self.filter_b = KalmanFilter(process_variance, measurement_variance)
        self.filter_c = KalmanFilter(process_variance, measurement_variance)
    
    def update(
        self, 
        coefficients: Optional[np.ndarray], 
        confidence: float = 1.0
    ) -> Optional[np.ndarray]:
        """
        Update filter with new lane coefficients.
        
        Args:
            coefficients: [a, b, c] for y = a*x^2 + b*x + c
            confidence: Detection confidence [0-1]
            
        Returns:
            Filtered coefficients or None
        """
        if coefficients is None:
            return None
        
        if len(coefficients) != 3:
            return coefficients  # Invalid format, return as-is
        
        # Update each coefficient
        a_filtered = self.filter_a.update(coefficients[0], confidence)
        b_filtered = self.filter_b.update(coefficients[1], confidence)
        c_filtered = self.filter_c.update(coefficients[2], confidence)
        
        return np.array([a_filtered, b_filtered, c_filtered])
    
    def reset(self):
        """Reset all filters."""
        self.filter_a.reset()
        self.filter_b.reset()
        self.filter_c.reset()


if __name__ == "__main__":
    # Test Kalman Filter
    import matplotlib.pyplot as plt
    
    # Simulate noisy measurements
    true_value = 5.0
    measurements = true_value + np.random.randn(100) * 0.5
    
    # Apply Kalman Filter
    kf = KalmanFilter(process_variance=0.01, measurement_variance=0.25)
    filtered = [kf.update(m) for m in measurements]
    
    # Plot results
    plt.figure(figsize=(12, 6))
    plt.plot(measurements, 'b.', alpha=0.3, label='Noisy measurements')
    plt.plot(filtered, 'r-', linewidth=2, label='Kalman filtered')
    plt.axhline(true_value, color='g', linestyle='--', label='True value')
    plt.legend()
    plt.title('Kalman Filter Smoothing')
    plt.xlabel('Time step')
    plt.ylabel('Value')
    plt.grid(True)
    plt.show()
    
    print("✓ Kalman Filter test complete")
