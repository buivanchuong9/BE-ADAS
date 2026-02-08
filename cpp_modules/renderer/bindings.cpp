#include "overlay.hpp"
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>

namespace py = pybind11;

namespace adas {

/**
 * pybind11 module for overlay renderer
 * Exposes C++ functions to Python with zero-copy NumPy array support
 */
PYBIND11_MODULE(renderer, m) {
    m.doc() = "High-performance overlay renderer for ADAS video processing";
    
    // BBox class
    py::class_<BBox>(m, "BBox")
        .def(py::init<>())
        .def(py::init<int, int, int, int, uint8_t, uint8_t, uint8_t, float, const std::string&>(),
             py::arg("x1"), py::arg("y1"), py::arg("x2"), py::arg("y2"),
             py::arg("r"), py::arg("g"), py::arg("b"),
             py::arg("confidence") = 0.0f,
             py::arg("label") = "")
        .def_readwrite("x1", &BBox::x1)
        .def_readwrite("y1", &BBox::y1)
        .def_readwrite("x2", &BBox::x2)
        .def_readwrite("y2", &BBox::y2)
        .def_readwrite("confidence", &BBox::confidence)
        .def_readwrite("label", &BBox::label)
        .def("__repr__", [](const BBox& b) {
            return "<BBox(" + std::to_string(b.x1) + "," + std::to_string(b.y1) + 
                   "," + std::to_string(b.x2) + "," + std::to_string(b.y2) + ")>";
        });
    
    // OverlayRenderer class
    py::class_<OverlayRenderer>(m, "OverlayRenderer")
        .def_static("render", 
            [](py::array_t<uint8_t> frame_bgr,
               py::object lane_mask_obj,
               const std::vector<BBox>& bboxes,
               float lane_alpha) {
                
                // Validate frame
                auto buf = frame_bgr.request();
                if (buf.ndim != 3) {
                    throw std::runtime_error("Frame must be 3D array (H×W×3)");
                }
                if (buf.shape[2] != 3) {
                    throw std::runtime_error("Frame must have 3 channels (BGR)");
                }
                
                int height = buf.shape[0];
                int width = buf.shape[1];
                uint8_t* frame_ptr = static_cast<uint8_t*>(buf.ptr);
                
                // Handle optional lane mask
                const uint8_t* mask_ptr = nullptr;
                if (!lane_mask_obj.is_none()) {
                    auto lane_mask = lane_mask_obj.cast<py::array_t<uint8_t>>();
                    auto mask_buf = lane_mask.request();
                    
                    if (mask_buf.ndim != 2) {
                        throw std::runtime_error("Lane mask must be 2D array (H×W)");
                    }
                    if (mask_buf.shape[0] != height || mask_buf.shape[1] != width) {
                        throw std::runtime_error("Lane mask size must match frame size");
                    }
                    
                    mask_ptr = static_cast<uint8_t*>(mask_buf.ptr);
                }
                
                // Release GIL for C++ computation
                py::gil_scoped_release release;
                
                // Call C++ renderer (IN-PLACE modification)
                OverlayRenderer::render(
                    frame_ptr,
                    height,
                    width,
                    mask_ptr,
                    bboxes,
                    lane_alpha
                );
                
                // Note: frame_bgr is modified in-place, no return needed
            },
            py::arg("frame_bgr"),
            py::arg("lane_mask") = py::none(),
            py::arg("bboxes") = std::vector<BBox>(),
            py::arg("lane_alpha") = 0.3f,
            R"pbdoc(
                Render overlays on frame IN-PLACE (zero-copy).
                
                Args:
                    frame_bgr (np.ndarray): Input/output BGR frame (H×W×3), uint8
                    lane_mask (np.ndarray, optional): Lane segmentation mask (H×W), uint8
                    bboxes (List[BBox]): Bounding boxes to draw
                    lane_alpha (float): Blending factor for lane mask (0.0-1.0)
                
                Returns:
                    None (modifies frame_bgr in-place)
                
                Example:
                    >>> import renderer
                    >>> import numpy as np
                    >>> frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
                    >>> mask = np.random.randint(0, 256, (1080, 1920), dtype=np.uint8)
                    >>> bboxes = [renderer.BBox(100, 100, 200, 200, 0, 255, 0, 0.95, "car")]
                    >>> renderer.OverlayRenderer.render(frame, mask, bboxes, 0.3)
                    >>> # frame is now modified with overlay
            )pbdoc"
        );
    
    // Version info
    m.attr("__version__") = "1.0.0";
    #ifdef __AVX2__
    m.attr("SIMD_ENABLED") = true;
    #else
    m.attr("SIMD_ENABLED") = false;
    #endif
}

} // namespace adas
