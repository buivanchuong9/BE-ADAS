#pragma once

#include <vector>
#include <string>
#include <cstdint>

namespace adas {

/**
 * Bounding box structure for object detection results
 */
struct BBox {
    int x1, y1, x2, y2;
    uint8_t color[3];  // BGR format
    float confidence;
    std::string label;
    
    BBox() : x1(0), y1(0), x2(0), y2(0), confidence(0.0f) {
        color[0] = color[1] = color[2] = 0;
    }
    
    BBox(int x1_, int y1_, int x2_, int y2_, 
         uint8_t r, uint8_t g, uint8_t b,
         float conf, const std::string& lbl)
        : x1(x1_), y1(y1_), x2(x2_), y2(y2_), 
          confidence(conf), label(lbl) {
        color[0] = b;  // OpenCV uses BGR
        color[1] = g;
        color[2] = r;
    }
};

/**
 * High-performance overlay renderer
 * CRITICAL: All operations are IN-PLACE (zero-copy)
 */
class OverlayRenderer {
public:
    /**
     * Render complete overlay on frame (IN-PLACE)
     * 
     * @param frame_bgr   Input/output BGR frame (H×W×3)
     * @param height      Frame height
     * @param width       Frame width
     * @param lane_mask   Optional lane segmentation mask (H×W), grayscale
     * @param bboxes      Object detection bounding boxes
     * @param lane_alpha  Blending factor for lane mask (0.0-1.0)
     * 
     * Thread-safety: Stateless, thread-safe
     * Performance: ~1.5-3ms per 1080p frame (SIMD optimized)
     */
    static void render(
        uint8_t* frame_bgr,
        int height, 
        int width,
        const uint8_t* lane_mask,
        const std::vector<BBox>& bboxes,
        float lane_alpha = 0.3f
    );
    
    /**
     * Blend lane mask with frame using SIMD (AVX2)
     * Applies colormap (JET-style) and alpha blending
     * 
     * OPTIMIZATION: Uses AVX2 intrinsics for 8-16x speedup
     */
    static void blend_lane_mask_simd(
        uint8_t* frame_bgr,
        const uint8_t* mask,
        int height,
        int width,
        float alpha
    );
    
    /**
     * Draw bounding boxes with labels (batch optimized)
     * Uses OpenCV's fast rectangle/text rendering
     */
    static void draw_bboxes(
        uint8_t* frame_bgr,
        int height,
        int width,
        const std::vector<BBox>& bboxes
    );
    
    /**
     * Apply colormap to grayscale mask (JET colormap)
     * Output: BGR image
     */
    static void apply_colormap_jet(
        const uint8_t* gray_input,
        uint8_t* bgr_output,
        int num_pixels
    );

private:
    // JET colormap lookup table (256 entries)
    static const uint8_t JET_COLORMAP[256][3];
    
    // Helper: Clamp value to [0, 255]
    static inline uint8_t clamp_u8(int val) {
        return (val < 0) ? 0 : (val > 255 ? 255 : static_cast<uint8_t>(val));
    }
};

} // namespace adas
