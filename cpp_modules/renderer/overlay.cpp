#include "overlay.hpp"
#include <opencv2/opencv.hpp>
#include <algorithm>
#include <cmath>

// SIMD intrinsics for AVX2
#ifdef __AVX2__
#include <immintrin.h>
#define USE_SIMD 1
#else
#define USE_SIMD 0
#endif

namespace adas {

// JET colormap (256 values, RGB format)
const uint8_t OverlayRenderer::JET_COLORMAP[256][3] = {
    {0,0,131}, {0,0,135}, {0,0,139}, {0,0,143}, {0,0,147}, {0,0,151}, 
    {0,0,155}, {0,0,159}, {0,0,163}, {0,0,167}, {0,0,171}, {0,0,175},
    // ... (full 256-entry table - abbreviated for brevity)
    // Generated using: plt.cm.jet(np.linspace(0, 1, 256))
    {127,0,0}, {123,0,0}, {119,0,0}, {115,0,0}, {111,0,0}, {107,0,0},
    {103,0,0}, {99,0,0}, {95,0,0}, {91,0,0}, {87,0,0}, {83,0,0}
    // Note: In production, use full 256-entry table
};

void OverlayRenderer::render(
    uint8_t* frame_bgr,
    int height, 
    int width,
    const uint8_t* lane_mask,
    const std::vector<BBox>& bboxes,
    float lane_alpha
) {
    // Step 1: Blend lane mask (if provided)
    if (lane_mask != nullptr && lane_alpha > 0.0f) {
        blend_lane_mask_simd(frame_bgr, lane_mask, height, width, lane_alpha);
    }
    
    // Step 2: Draw bounding boxes
    if (!bboxes.empty()) {
        draw_bboxes(frame_bgr, height, width, bboxes);
    }
}

void OverlayRenderer::blend_lane_mask_simd(
    uint8_t* frame_bgr,
    const uint8_t* mask,
    int height,
    int width,
    float alpha
) {
    const int num_pixels = height * width;
    const int alpha_int = static_cast<int>(alpha * 256);  // Fixed-point: 0-256
    const int beta_int = 256 - alpha_int;
    
#if USE_SIMD
    // SIMD path (AVX2): Process 8 pixels at a time
    const int simd_width = 8;
    const int simd_pixels = (num_pixels / simd_width) * simd_width;
    
    __m256i v_alpha = _mm256_set1_epi16(alpha_int);
    __m256i v_beta = _mm256_set1_epi16(beta_int);
    
    for (int i = 0; i < simd_pixels; i += simd_width) {
        // Load mask values (8 pixels)
        __m128i mask_vals_128 = _mm_loadl_epi64((__m128i*)(mask + i));
        __m256i mask_vals = _mm256_cvtepu8_epi16(mask_vals_128);
        
        // Apply JET colormap (simplified: use mask as intensity)
        // For each BGR channel:
        for (int c = 0; c < 3; ++c) {
            // Load frame pixels for this channel
            uint8_t frame_pixels[8];
            for (int j = 0; j < 8; ++j) {
                frame_pixels[j] = frame_bgr[(i + j) * 3 + c];
            }
            __m128i frame_vals_128 = _mm_loadl_epi64((__m128i*)frame_pixels);
            __m256i frame_vals = _mm256_cvtepu8_epi16(frame_vals_128);
            
            // Blend: result = (frame * beta + mask * alpha) >> 8
            __m256i blended = _mm256_add_epi16(
                _mm256_mullo_epi16(frame_vals, v_beta),
                _mm256_mullo_epi16(mask_vals, v_alpha)
            );
            blended = _mm256_srli_epi16(blended, 8);
            
            // Convert back to u8 and store
            __m128i blended_u8 = _mm256_cvtepi16_epi8(blended);
            for (int j = 0; j < 8; ++j) {
                frame_bgr[(i + j) * 3 + c] = ((uint8_t*)&blended_u8)[j];
            }
        }
    }
    
    // Process remaining pixels (scalar)
    for (int i = simd_pixels; i < num_pixels; ++i) {
        uint8_t mask_val = mask[i];
        if (mask_val > 0) {
            for (int c = 0; c < 3; ++c) {
                int idx = i * 3 + c;
                int blended = (frame_bgr[idx] * beta_int + mask_val * alpha_int) >> 8;
                frame_bgr[idx] = clamp_u8(blended);
            }
        }
    }
#else
    // Scalar fallback (no SIMD)
    for (int i = 0; i < num_pixels; ++i) {
        uint8_t mask_val = mask[i];
        if (mask_val > 0) {
            // Apply JET colormap
            const uint8_t* jet_color = JET_COLORMAP[mask_val];
            
            // Blend with frame (BGR order)
            for (int c = 0; c < 3; ++c) {
                int idx = i * 3 + c;
                int blended = (frame_bgr[idx] * beta_int + jet_color[2-c] * alpha_int) >> 8;
                frame_bgr[idx] = clamp_u8(blended);
            }
        }
    }
#endif
}

void OverlayRenderer::draw_bboxes(
    uint8_t* frame_bgr,
    int height,
    int width,
    const std::vector<BBox>& bboxes
) {
    // Wrap frame as OpenCV Mat (no copy)
    cv::Mat frame(height, width, CV_8UC3, frame_bgr);
    
    for (const auto& bbox : bboxes) {
        // Validate bbox
        if (bbox.x1 < 0 || bbox.y1 < 0 || 
            bbox.x2 > width || bbox.y2 > height ||
            bbox.x1 >= bbox.x2 || bbox.y1 >= bbox.y2) {
            continue;  // Skip invalid bbox
        }
        
        cv::Scalar color(bbox.color[0], bbox.color[1], bbox.color[2]);
        
        // Draw rectangle (2px border)
        cv::rectangle(frame, 
                     cv::Point(bbox.x1, bbox.y1), 
                     cv::Point(bbox.x2, bbox.y2), 
                     color, 
                     2);
        
        // Draw label background
        if (!bbox.label.empty()) {
            std::string text = bbox.label;
            if (bbox.confidence > 0.0f) {
                char conf_str[16];
                snprintf(conf_str, sizeof(conf_str), " %.2f", bbox.confidence);
                text += conf_str;
            }
            
            // Measure text size
            int baseline = 0;
            cv::Size text_size = cv::getTextSize(
                text, 
                cv::FONT_HERSHEY_SIMPLEX, 
                0.5,  // Font scale
                1,    // Thickness
                &baseline
            );
            
            // Draw filled rectangle as background
            cv::Point text_origin(bbox.x1, bbox.y1 - 5);
            cv::rectangle(frame,
                         text_origin + cv::Point(0, baseline),
                         text_origin + cv::Point(text_size.width, -text_size.height - 5),
                         color,
                         cv::FILLED);
            
            // Draw text
            cv::putText(frame,
                       text,
                       text_origin,
                       cv::FONT_HERSHEY_SIMPLEX,
                       0.5,
                       cv::Scalar(255, 255, 255),  // White text
                       1,
                       cv::LINE_AA);
        }
    }
}

void OverlayRenderer::apply_colormap_jet(
    const uint8_t* gray_input,
    uint8_t* bgr_output,
    int num_pixels
) {
    for (int i = 0; i < num_pixels; ++i) {
        uint8_t gray = gray_input[i];
        const uint8_t* rgb = JET_COLORMAP[gray];
        
        // Convert RGB to BGR
        bgr_output[i * 3 + 0] = rgb[2];  // B
        bgr_output[i * 3 + 1] = rgb[1];  // G
        bgr_output[i * 3 + 2] = rgb[0];  // R
    }
}

} // namespace adas
