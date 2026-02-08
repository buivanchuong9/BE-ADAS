/**
 * HLS Encoder Implementation
 */

#include "encoder.hpp"
#include <iostream>
#include <sstream>
#include <fstream>
#include <iomanip>
#include <cmath>

namespace adas {
namespace hlsenc {

HLSEncoder::HLSEncoder(
    const std::string& output_dir,
    int width,
    int height,
    double fps,
    double segment_duration
)
    : fmt_ctx_(nullptr)
    , codec_ctx_(nullptr)
    , stream_(nullptr)
    , sws_ctx_(nullptr)
    , yuv_frame_(nullptr)
    , packet_(nullptr)
    , output_dir_(output_dir)
    , width_(width)
    , height_(height)
    , fps_(fps)
    , segment_duration_(segment_duration)
    , current_segment_idx_(0)
    , frames_in_current_segment_(0)
    , total_frames_encoded_(0)
    , total_segments_written_(0)
    , encoder_name_("unknown")
{
    frames_per_segment_ = static_cast<int>(std::round(fps * segment_duration));
    playlist_path_ = output_dir + "/playlist.m3u8";
    
    init_encoder();
}

HLSEncoder::~HLSEncoder() {
    if (yuv_frame_) {
        av_frame_free(&yuv_frame_);
    }
    if (packet_) {
        av_packet_free(&packet_);
    }
    if (sws_ctx_) {
        sws_freeContext(sws_ctx_);
    }
    if (codec_ctx_) {
        avcodec_free_context(&codec_ctx_);
    }
    if (fmt_ctx_) {
        if (fmt_ctx_->pb) {
            avio_closep(&fmt_ctx_->pb);
        }
        avformat_free_context(fmt_ctx_);
    }
}

void HLSEncoder::init_encoder() {
    // Try GPU encoder first (NVENC), fallback to CPU if unavailable
    const AVCodec* codec = nullptr;
    bool using_nvenc = false;
    
    // 1. Try NVENC (GPU hardware encoder)
    codec = avcodec_find_encoder_by_name("h264_nvenc");
    if (codec) {
        std::cout << "✅ Using NVIDIA NVENC GPU encoder (h264_nvenc)\n";
        using_nvenc = true;
        encoder_name_ = "h264_nvenc";
    } else {
        // 2. Fallback to CPU encoder
        std::cout << "⚠️  NVENC not available, using CPU encoder (libx264)\n";
        codec = avcodec_find_encoder(AV_CODEC_ID_H264);
        if (!codec) {
            throw std::runtime_error("No H.264 encoder found (neither NVENC nor libx264)");
        }
        encoder_name_ = "libx264";
    }
    
    // Allocate codec context
    codec_ctx_ = avcodec_alloc_context3(codec);
    if (!codec_ctx_) {
        throw std::runtime_error("Failed to allocate codec context");
    }
    
    // Configure encoder (common settings)
    codec_ctx_->width = width_;
    codec_ctx_->height = height_;
    codec_ctx_->time_base = AVRational{1, static_cast<int>(fps_)};
    codec_ctx_->framerate = AVRational{static_cast<int>(fps_), 1};
    codec_ctx_->pix_fmt = AV_PIX_FMT_YUV420P;
    codec_ctx_->gop_size = 30;  // Keyframe every 1 second
    codec_ctx_->max_b_frames = 0;  // Low latency
    codec_ctx_->bit_rate = width_ * height_ * 2;  // ~2 bits per pixel
    
    // Encoder-specific settings
    if (using_nvenc) {
        // NVENC GPU settings
        // Use legacy presets for compatibility with older FFmpeg versions (4.x)
        // "llhp" = Low Latency High Performance (equivalent to "p1"/"p2" on newer drivers)
        av_opt_set(codec_ctx_->priv_data, "preset", "llhp", 0); 
        
        av_opt_set(codec_ctx_->priv_data, "rc", "cbr", 0);       // Constant bitrate
        av_opt_set(codec_ctx_->priv_data, "zerolatency", "1", 0); // Zero latency
        av_opt_set(codec_ctx_->priv_data, "delay", "0", 0);
        
        // Ensure no B-frames
        codec_ctx_->max_b_frames = 0;
    } else {
        // CPU libx264 settings (For macOS dev only)
        av_opt_set(codec_ctx_->priv_data, "preset", "veryfast", 0);
        av_opt_set(codec_ctx_->priv_data, "tune", "zerolatency", 0);
    }
    
    // Open codec
    int ret = avcodec_open2(codec_ctx_, codec, nullptr);
    if (ret < 0) {
        char errbuf[AV_ERROR_MAX_STRING_SIZE];
        av_strerror(ret, errbuf, sizeof(errbuf));
        
        std::cerr << "❌ FAILED TO OPEN ENCODER: " << (using_nvenc ? "NVENC" : "CPU") << "\n";
        std::cerr << "   Error code: " << ret << "\n";
        std::cerr << "   Error msg:  " << errbuf << "\n";
        
        if (using_nvenc) {
             // STRICT MODE: If we found NVENC but failed to open it -> THROW ERROR.
             // Do NOT fallback to CPU. Force user to fix NVENC config.
             throw std::runtime_error(std::string("CRITICAL: Found NVENC hardware but failed to open it! Error: ") + errbuf);
        } else {
             throw std::runtime_error(std::string("Failed to open codec: ") + errbuf);
        }
    }
    
    // Allocate YUV frame
    yuv_frame_ = av_frame_alloc();
    if (!yuv_frame_) {
        throw std::runtime_error("Failed to allocate YUV frame");
    }
    
    yuv_frame_->format = codec_ctx_->pix_fmt;
    yuv_frame_->width = width_;
    yuv_frame_->height = height_;
    
    ret = av_frame_get_buffer(yuv_frame_, 0);
    if (ret < 0) {
        throw std::runtime_error("Failed to allocate YUV frame buffer");
    }
    
    // Initialize swscale context (BGR → YUV420p)
    sws_ctx_ = sws_getContext(
        width_, height_, AV_PIX_FMT_BGR24,
        width_, height_, AV_PIX_FMT_YUV420P,
        SWS_BILINEAR, nullptr, nullptr, nullptr
    );
    
    if (!sws_ctx_) {
        throw std::runtime_error("Failed to create swscale context");
    }
    
    // Allocate packet
    packet_ = av_packet_alloc();
    if (!packet_) {
        throw std::runtime_error("Failed to allocate packet");
    }
    
    // Open first segment
    open_segment();
}

void HLSEncoder::open_segment() {
    // Generate segment filename
    std::ostringstream oss;
    oss << output_dir_ << "/segment_" 
        << std::setw(5) << std::setfill('0') << current_segment_idx_ 
        << ".ts";
    std::string segment_path = oss.str();
    
    // Allocate format context
    int ret = avformat_alloc_output_context2(&fmt_ctx_, nullptr, "mpegts", segment_path.c_str());
    if (ret < 0) {
        throw std::runtime_error("Failed to allocate format context");
    }
    
    // Create stream
    stream_ = avformat_new_stream(fmt_ctx_, nullptr);
    if (!stream_) {
        throw std::runtime_error("Failed to create stream");
    }
    
    stream_->time_base = codec_ctx_->time_base;
    ret = avcodec_parameters_from_context(stream_->codecpar, codec_ctx_);
    if (ret < 0) {
        throw std::runtime_error("Failed to copy codec parameters");
    }
    
    // Open output file
    ret = avio_open(&fmt_ctx_->pb, segment_path.c_str(), AVIO_FLAG_WRITE);
    if (ret < 0) {
        char errbuf[AV_ERROR_MAX_STRING_SIZE];
        av_strerror(ret, errbuf, sizeof(errbuf));
        throw std::runtime_error(std::string("Failed to open output file: ") + errbuf);
    }
    
    // Write header
    ret = avformat_write_header(fmt_ctx_, nullptr);
    if (ret < 0) {
        throw std::runtime_error("Failed to write format header");
    }
}

void HLSEncoder::close_segment() {
    if (!fmt_ctx_) return;
    
    // Write trailer
    av_write_trailer(fmt_ctx_);
    
    // Close file
    if (fmt_ctx_->pb) {
        avio_closep(&fmt_ctx_->pb);
    }
    
    // Generate segment filename for playlist
    std::ostringstream oss;
    oss << "segment_" << std::setw(5) << std::setfill('0') << current_segment_idx_ << ".ts";
    segment_filenames_.push_back(oss.str());
    
    // Free format context
    avformat_free_context(fmt_ctx_);
    fmt_ctx_ = nullptr;
    stream_ = nullptr;
    
    total_segments_written_++;
}

void HLSEncoder::encode_frame(const uint8_t* bgr_data, int64_t pts) {
    // Convert BGR → YUV420p
    const uint8_t* src_data[1] = { bgr_data };
    int src_linesize[1] = { width_ * 3 };
    
    sws_scale(
        sws_ctx_,
        src_data, src_linesize,
        0, height_,
        yuv_frame_->data, yuv_frame_->linesize
    );
    
    // Set PTS
    yuv_frame_->pts = pts;
    
    // Encode
    encode_yuv_frame(yuv_frame_, pts);
    
    total_frames_encoded_++;
    frames_in_current_segment_++;
    
    // Check if segment is complete
    if (frames_in_current_segment_ >= frames_per_segment_) {
        flush_segment();
    }
}

void HLSEncoder::encode_yuv_frame(AVFrame* frame, int64_t pts) {
    // Send frame to encoder
    int ret = avcodec_send_frame(codec_ctx_, frame);
    if (ret < 0) {
        throw std::runtime_error("Failed to send frame to encoder");
    }
    
    // Receive encoded packets
    while (ret >= 0) {
        ret = avcodec_receive_packet(codec_ctx_, packet_);
        if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) {
            break;
        } else if (ret < 0) {
            throw std::runtime_error("Failed to receive packet from encoder");
        }
        
        // Rescale packet timestamps
        av_packet_rescale_ts(packet_, codec_ctx_->time_base, stream_->time_base);
        packet_->stream_index = stream_->index;
        
        // Write packet to segment
        ret = av_interleaved_write_frame(fmt_ctx_, packet_);
        if (ret < 0) {
            throw std::runtime_error("Failed to write packet");
        }
        
        av_packet_unref(packet_);
    }
}

std::string HLSEncoder::flush_segment() {
    if (frames_in_current_segment_ == 0) {
        return "";
    }
    
    // DON'T flush encoder here - it causes EOF state
    // Just close the muxer (format context)
    
    //  Close current segment
    close_segment();
    
    // Update playlist
    write_playlist();
    
    // Prepare next segment
    std::string flushed_segment = segment_filenames_.back();
    current_segment_idx_++;
    frames_in_current_segment_ = 0;
    
    // Open next segment (ready for more frames)
    open_segment();
    
    return flushed_segment;
}

void HLSEncoder::finalize() {
    // Flush encoder (send NULL frame)
    avcodec_send_frame(codec_ctx_, nullptr);
    
    // Receive remaining packets
    int ret;
    while (true) {
        ret = avcodec_receive_packet(codec_ctx_, packet_);
        if (ret == AVERROR(EAGAIN) || ret == AVERROR_EOF) {
            break;
        } else if (ret < 0) {
            // Ignore errors during finalize
            break;
        }
        
        if (fmt_ctx_ && stream_) {
            av_packet_rescale_ts(packet_, codec_ctx_->time_base, stream_->time_base);
            packet_->stream_index = stream_->index;
            av_interleaved_write_frame(fmt_ctx_, packet_);
        }
        av_packet_unref(packet_);
    }
    
    // Flush any remaining frames in buffer
    if (frames_in_current_segment_ > 0) {
        close_segment();
        write_playlist();
    } else if (fmt_ctx_) {
        // Close last segment if still open
        close_segment();
    }
    
    // Write final playlist with ENDLIST marker
    std::ofstream playlist(playlist_path_, std::ios::app);
    if (playlist.is_open()) {
        playlist << "#EXT-X-ENDLIST\n";
        playlist.close();
    }
}

void HLSEncoder::write_playlist() {
    // Atomic write: write to temp → rename
    std::string temp_path = playlist_path_ + ".tmp";
    
    std::ofstream playlist(temp_path);
    if (!playlist.is_open()) {
        throw std::runtime_error("Failed to open playlist for writing");
    }
    
    // HLS header
    playlist << "#EXTM3U\n";
    playlist << "#EXT-X-VERSION:3\n";
    playlist << "#EXT-X-TARGETDURATION:" << static_cast<int>(segment_duration_) + 1 << "\n";
    playlist << "#EXT-X-MEDIA-SEQUENCE:0\n";
    
    // Write all segments
    for (const auto& seg : segment_filenames_) {
        playlist << "#EXTINF:" << std::fixed << std::setprecision(3) << segment_duration_ << ",\n";
        playlist << seg << "\n";
    }
    
    playlist.close();
    
    // Atomic rename
    std::rename(temp_path.c_str(), playlist_path_.c_str());
}

HLSEncoder::Stats HLSEncoder::get_stats() const {
    return Stats{
        total_frames_encoded_,
        total_segments_written_,
        frames_in_current_segment_
    };
}

} // namespace hlsenc
} // namespace adas
