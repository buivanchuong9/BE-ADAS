/**
 * HLS Encoder C++ Module - Hardware-Accelerated Video Encoding
 * ==============================================================
 * Direct FFmpeg libav* API for zero-copy HLS segment generation.
 * 
 * PERFORMANCE TARGET:
 * - Python subprocess: 150-200ms per segment
 * - C++ direct API:     50-60ms per segment (3x faster)
 * 
 * Author: Principal Software Architect
 * Date: 2026-02-08
 */

#pragma once

extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libswscale/swscale.h>
#include <libavutil/opt.h>
#include <libavutil/imgutils.h>
}

#include <string>
#include <vector>
#include <stdexcept>
#include <memory>

namespace adas {
namespace hlsenc {

/**
 * HLS Encoder - Stateful encoder with persistent context
 * 
 * DESIGN:
 * - Persistent AVCodecContext (no re-init per segment)
 * - Zero-copy BGR→YUV420p conversion via SwsContext
 * - Direct .ts segment writing
 * - Atomic playlist updates
 */
class HLSEncoder {
public:
    /**
     * Initialize encoder.
     * 
     * @param output_dir  Output directory for segments
     * @param width       Frame width
     * @param height      Frame height
     * @param fps         Frames per second
     * @param segment_duration  Segment duration in seconds (default 2.0)
     */
    HLSEncoder(
        const std::string& output_dir,
        int width,
        int height,
        double fps,
        double segment_duration = 2.0
    );
    
    ~HLSEncoder();
    
    // Delete copy/move (encoder has unique state)
    HLSEncoder(const HLSEncoder&) = delete;
    HLSEncoder& operator=(const HLSEncoder&) = delete;
    
    /**
     * Encode one frame (BGR format from OpenCV).
     * 
     * @param bgr_data  Frame data pointer (H×W×3 BGR uint8)
     * @param pts       Presentation timestamp (frame index)
     */
    void encode_frame(const uint8_t* bgr_data, int64_t pts);
    
    /**
     * Flush current segment to .ts file.
     * Called automatically every segment_duration seconds.
     * 
     * @return Segment filename
     */
    std::string flush_segment();
    
    /**
     * Finalize encoding (close files, write playlist end marker).
     */
    void finalize();
    
    /**
     * Get current statistics.
     */
    struct Stats {
        int total_frames_encoded;
        int total_segments_written;
        int frames_in_current_segment;
    };
    
    Stats get_stats() const;
    
private:
    // FFmpeg contexts
    AVFormatContext* fmt_ctx_;
    AVCodecContext* codec_ctx_;
    AVStream* stream_;
    SwsContext* sws_ctx_;
    
    // Frame buffers
    AVFrame* yuv_frame_;
    AVPacket* packet_;
    
    // State
    std::string output_dir_;
    int width_;
    int height_;
    double fps_;
    double segment_duration_;
    int frames_per_segment_;
    
    // Counters
    int current_segment_idx_;
    int frames_in_current_segment_;
    int total_frames_encoded_;
    int total_segments_written_;
    
    // Segment tracking
    std::vector<std::string> segment_filenames_;
    std::string playlist_path_;
    
    // Helper functions
    void init_encoder();
    void open_segment();
    void close_segment();
    void write_playlist();
    void encode_yuv_frame(AVFrame* frame, int64_t pts);
};

} // namespace hlsenc
} // namespace adas
