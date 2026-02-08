/**
 * Python bindings for HLS Encoder
 */

#include "encoder.hpp"
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>

namespace py = pybind11;
using namespace adas::hlsenc;

PYBIND11_MODULE(hlsenc, m) {
    m.doc() = "High-performance HLS encoder using FFmpeg libav* API";
    
    m.attr("__version__") = "1.0.0";
    m.attr("FFMPEG_BACKEND") = true;
    
    // Stats struct
    py::class_<HLSEncoder::Stats>(m, "Stats")
        .def_readonly("total_frames_encoded", &HLSEncoder::Stats::total_frames_encoded)
        .def_readonly("total_segments_written", &HLSEncoder::Stats::total_segments_written)
        .def_readonly("frames_in_current_segment", &HLSEncoder::Stats::frames_in_current_segment)
        .def("__repr__", [](const HLSEncoder::Stats& s) {
            return "<Stats frames=" + std::to_string(s.total_frames_encoded) +
                   " segments=" + std::to_string(s.total_segments_written) + ">";
        });
    
    // HLSEncoder class
    py::class_<HLSEncoder>(m, "HLSEncoder")
        .def(py::init<const std::string&, int, int, double, double>(),
             py::arg("output_dir"),
             py::arg("width"),
             py::arg("height"),
             py::arg("fps"),
             py::arg("segment_duration") = 2.0,
             R"pbdoc(
                Initialize HLS encoder.
                
                Args:
                    output_dir: Output directory for segments
                    width: Frame width
                    height: Frame height
                    fps: Frames per second
                    segment_duration: Segment duration in seconds (default 2.0)
                
                Raises:
                    RuntimeError: If FFmpeg initialization fails
             )pbdoc")
        
        .def("encode_frame", [](HLSEncoder& self, py::array_t<uint8_t> frame, int64_t pts) {
            // Validate input
            auto buf = frame.request();
            if (buf.ndim != 3) {
                throw std::runtime_error("Frame must be 3D array (H×W×3)");
            }
            if (buf.shape[2] != 3) {
                throw std::runtime_error("Frame must have 3 channels (BGR)");
            }
            
            // Get raw pointer
            const uint8_t* data = static_cast<const uint8_t*>(buf.ptr);
            
            // Release GIL during encoding (allow Python parallelism)
            py::gil_scoped_release release;
            
            // Encode
            self.encode_frame(data, pts);
        },
        py::arg("frame"),
        py::arg("pts"),
        R"pbdoc(
            Encode one frame.
            
            Args:
                frame: NumPy array (H×W×3) BGR uint8
                pts: Presentation timestamp (frame index)
        )pbdoc")
        
        .def("flush_segment", &HLSEncoder::flush_segment,
             R"pbdoc(
                Flush current segment to .ts file.
                
                Returns:
                    Segment filename
             )pbdoc")
        
        .def("finalize", &HLSEncoder::finalize,
             R"pbdoc(
                Finalize encoding (close files, write playlist end marker).
             )pbdoc")
        
        .def("get_stats", &HLSEncoder::get_stats,
             R"pbdoc(
                Get current statistics.
                
                Returns:
                    Stats object
             )pbdoc");
}
