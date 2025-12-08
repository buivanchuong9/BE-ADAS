import numpy as np
from collections import deque
import copy
from .kalman_filter import KalmanFilter
from scipy.optimize import linear_sum_assignment

class STrack:
    shared_kalman = KalmanFilter()

    def __init__(self, tlwh, score, class_id):
        # wait activate
        self._tlwh = np.asarray(tlwh, dtype=np.float32)
        self.kalman_filter = None
        self.mean, self.covariance = None, None
        self.is_activated = False

        self.score = score
        self.class_id = class_id
        self.tracklet_len = 0
        self.track_id = 0
        self.state = 1 # TrackState.New
        self.frame_id = 0
        self.start_frame = 0

    def predict(self):
        mean_state = self.mean.copy()
        if self.state != 1: # TrackState.Tracked
            self.mean, self.covariance = self.shared_kalman.predict(mean_state, self.covariance)

    def activate(self, kalman_filter, frame_id):
        """Start a new tracklet"""
        self.kalman_filter = kalman_filter
        self.track_id = self.next_id()
        self.mean, self.covariance = self.kalman_filter.initiate(self.tlwh_to_xyah(self._tlwh))

        self.tracklet_len = 0
        self.state = 1 # TrackState.Tracked
        if frame_id == 1:
            self.is_activated = True
        self.frame_id = frame_id
        self.start_frame = frame_id

    def re_activate(self, new_track, frame_id, new_id=False):
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlwh_to_xyah(new_track.tlwh)
        )
        self.tracklet_len = 0
        self.state = 1 # TrackState.Tracked
        self.is_activated = True
        self.frame_id = frame_id
        if new_id:
            self.track_id = self.next_id()
        self.score = new_track.score
        self.class_id = new_track.class_id

    def update(self, new_track, frame_id):
        """
        Update a matched track
        :type new_track: STrack
        :type frame_id: int
        :type update_feature: bool
        :return:
        """
        self.frame_id = frame_id
        self.tracklet_len += 1

        new_tlwh = new_track.tlwh
        self.mean, self.covariance = self.kalman_filter.update(
            self.mean, self.covariance, self.tlwh_to_xyah(new_tlwh)
        )
        self.state = 1 # TrackState.Tracked
        self.is_activated = True

        self.score = new_track.score
        self.class_id = new_track.class_id

    @property
    def tlwh(self):
        """Get current position in bounding box format `(top left x, top left y,
        width, height)`.
        """
        if self.mean is None:
            return self._tlwh.copy()
        ret = self.mean[:4].copy()
        ret[2] *= ret[3]
        ret[:2] -= ret[2:] / 2
        return ret

    @property
    def tlbr(self):
        """Convert bounding box to format `(min x, min y, max x, max y)`, i.e.,
        `(top left, bottom right)`.
        """
        ret = self.tlwh.copy()
        ret[2:] += ret[:2]
        return ret

    @staticmethod
    def tlwh_to_xyah(tlwh):
        """Convert bounding box to format `(center x, center y, aspect ratio,
        height)`, where the aspect ratio is `width / height`.
        """
        ret = np.asarray(tlwh).copy()
        ret[:2] += ret[2:] / 2
        ret[2] /= ret[3]
        return ret

    def __repr__(self):
        return 'OT_{}_({}-{})'.format(self.track_id, self.start_frame, self.end_frame)

    @staticmethod
    def next_id():
        # Simple static counter
        if not hasattr(STrack, '_count'):
            STrack._count = 0
        STrack._count += 1
        return STrack._count

class ByteTrack:
    def __init__(self, track_thresh=0.5, track_buffer=30, match_thresh=0.8, frame_rate=30):
        self.track_thresh = track_thresh
        self.track_buffer = track_buffer
        self.match_thresh = match_thresh
        self.frame_rate = frame_rate

        self.tracked_stracks = []  # type: list[STrack]
        self.lost_stracks = []  # type: list[STrack]
        self.removed_stracks = []  # type: list[STrack]

        self.frame_id = 0
        self.kalman_filter = KalmanFilter()

    def update(self, output_results):
        """
        Update tracking with new detections
        output_results: list of [x1, y1, x2, y2, score, class_id]
        """
        self.frame_id += 1
        activated_stracks = []
        refind_stracks = []
        lost_stracks = []
        removed_stracks = []

        # Parse detections
        if len(output_results) == 0:
            detections = []
            detections_low = []
        else:
            # Separate detections into high score and low score
            scores = output_results[:, 4]
            bboxes = output_results[:, :4]  # x1, y1, x2, y2
            classes = output_results[:, 5]

            # Convert to tlwh
            tlwhs = []
            for bbox in bboxes:
                tlwhs.append([bbox[0], bbox[1], bbox[2] - bbox[0], bbox[3] - bbox[1]])
            tlwhs = np.array(tlwhs)

            remain_inds = scores > self.track_thresh
            inds_low = scores > 0.1
            inds_high = scores < self.track_thresh

            inds_second = np.logical_and(inds_low, inds_high)
            
            dets_first = []
            dets_second = []
            
            if len(tlwhs) > 0:
                dets_first = [STrack(tlwhs[i], scores[i], classes[i]) for i in range(len(tlwhs)) if remain_inds[i]]
                dets_second = [STrack(tlwhs[i], scores[i], classes[i]) for i in range(len(tlwhs)) if inds_second[i]]

        # Add unconfirmed tracks to tracked_stracks for matching
        unconfirmed = []
        tracked_stracks = []  # type: list[STrack]
        for track in self.tracked_stracks:
            if not track.is_activated:
                unconfirmed.append(track)
            else:
                tracked_stracks.append(track)

        # Step 2: First association, with high score detection boxes
        strack_pool = join_stracks(tracked_stracks, self.lost_stracks)
        
        # Predict current location with KF
        for track in strack_pool:
            track.predict()

        dists = iou_distance(strack_pool, dets_first)
        matches, u_track, u_detection = linear_assignment(dists, thresh=self.match_thresh)

        for itracked, idet in matches:
            track = strack_pool[itracked]
            det = dets_first[idet]
            if track.state == 1: # TrackState.Tracked
                track.update(det, self.frame_id)
                activated_stracks.append(track)
            else:
                track.re_activate(det, self.frame_id, new_id=False)
                refind_stracks.append(track)

        # Step 3: Second association, with low score detection boxes
        r_tracked_stracks = [strack_pool[i] for i in u_track if strack_pool[i].state == 1]
        dists = iou_distance(r_tracked_stracks, dets_second)
        matches, u_track, u_detection_second = linear_assignment(dists, thresh=0.5)

        for itracked, idet in matches:
            track = r_tracked_stracks[itracked]
            det = dets_second[idet]
            if track.state == 1:
                track.update(det, self.frame_id)
                activated_stracks.append(track)
            else:
                track.re_activate(det, self.frame_id, new_id=False)
                refind_stracks.append(track)

        for it in u_track:
            track = r_tracked_stracks[it]
            if not track.state == 2: # TrackState.Lost
                track.state = 2 # TrackState.Lost
                lost_stracks.append(track)

        # Deal with unconfirmed tracks, usually tracks with only one beginning frame
        detections = [dets_first[i] for i in u_detection]
        dists = iou_distance(unconfirmed, detections)
        matches, u_unconfirmed, u_detection = linear_assignment(dists, thresh=0.7)

        for itracked, idet in matches:
            unconfirmed[itracked].update(detections[idet], self.frame_id)
            activated_stracks.append(unconfirmed[itracked])

        for it in u_unconfirmed:
            track = unconfirmed[it]
            track.state = 3 # TrackState.Removed
            removed_stracks.append(track)

        # Step 4: Init new stracks
        forin_new = [detections[i] for i in u_detection]
        for track in forin_new:
            if track.score < self.track_thresh:
                continue
            track.activate(self.kalman_filter, self.frame_id)
            activated_stracks.append(track)

        # Step 5: Update state
        for track in self.lost_stracks:
            if self.frame_id - track.frame_id > self.track_buffer:
                track.state = 3 # TrackState.Removed
                removed_stracks.append(track)

        self.tracked_stracks = [t for t in self.tracked_stracks if t.state == 1]
        self.tracked_stracks = join_stracks(self.tracked_stracks, activated_stracks)
        self.tracked_stracks = join_stracks(self.tracked_stracks, refind_stracks)
        self.lost_stracks = sub_stracks(self.lost_stracks, self.tracked_stracks)
        self.lost_stracks.extend(lost_stracks)
        self.lost_stracks = sub_stracks(self.lost_stracks, self.removed_stracks)
        self.removed_stracks.extend(removed_stracks)
        self.tracked_stracks, self.lost_stracks = remove_duplicate_stracks(self.tracked_stracks, self.lost_stracks)
        
        # Return current tracks
        output_stracks = [track for track in self.tracked_stracks if track.is_activated]
        return output_stracks


# ================= Helper Functions =================

def join_stracks(tlista, tlistb):
    exists = {}
    res = []
    for t in tlista:
        exists[t.track_id] = 1
        res.append(t)
    for t in tlistb:
        tid = t.track_id
        if not exists.get(tid, 0):
            exists[tid] = 1
            res.append(t)
    return res

def sub_stracks(tlista, tlistb):
    stracks = {}
    for t in tlista:
        stracks[t.track_id] = t
    for t in tlistb:
        tid = t.track_id
        if stracks.get(tid, 0):
            del stracks[tid]
    return list(stracks.values())

def remove_duplicate_stracks(stracksa, stracksb):
    pdist = iou_distance(stracksa, stracksb)
    pairs = np.where(pdist < 0.15)
    dupa, dupb = pairs
    for a, b in zip(dupa, dupb):
        timep = stracksa[a].frame_id - stracksa[a].start_frame
        timeq = stracksb[b].frame_id - stracksb[b].start_frame
        if timep > timeq:
            stracksb[b].state = 3 # Removed
        else:
            stracksa[a].state = 3 # Removed
    return [t for t in stracksa if t.state != 3], [t for t in stracksb if t.state != 3]

def iou_distance(atracks, btracks):
    """
    Compute cost based on IoU
    :type atracks: list[STrack]
    :type btracks: list[STrack]
    :rtype cost_matrix np.ndarray
    """

    if (len(atracks)>0 and isinstance(atracks[0], np.ndarray)) or (len(btracks) > 0 and isinstance(btracks[0], np.ndarray)):
        atlbrs = atracks
        btlbrs = btracks
    else:
        atlbrs = [track.tlbr for track in atracks]
        btlbrs = [track.tlbr for track in btracks]
    
    _ious = ious(atlbrs, btlbrs)
    cost_matrix = 1 - _ious
    
    return cost_matrix

def ious(atlbrs, btlbrs):
    """
    Compute cost based on IoU
    :type atlbrs: list[tlbr] | np.ndarray
    :type btlbrs: list[tlbr] | np.ndarray
    :rtype ious np.ndarray
    """
    ious = np.zeros((len(atlbrs), len(btlbrs)), dtype=np.float32)
    if len(atlbrs) * len(btlbrs) == 0:
        return ious

    ious = bbox_ious(
        np.ascontiguousarray(atlbrs, dtype=np.float32),
        np.ascontiguousarray(btlbrs, dtype=np.float32)
    )

    return ious

def bbox_ious(boxes1, boxes2):
    """
    Compute IOU between two sets of boxes
    """
    b1_x1, b1_y1, b1_x2, b1_y2 = boxes1[:, 0], boxes1[:, 1], boxes1[:, 2], boxes1[:, 3]
    b2_x1, b2_y1, b2_x2, b2_y2 = boxes2[:, 0], boxes2[:, 1], boxes2[:, 2], boxes2[:, 3]

    # Intersection area
    inter_rect_x1 = np.maximum(b1_x1[:, None], b2_x1)
    inter_rect_y1 = np.maximum(b1_y1[:, None], b2_y1)
    inter_rect_x2 = np.minimum(b1_x2[:, None], b2_x2)
    inter_rect_y2 = np.minimum(b1_y2[:, None], b2_y2)

    inter_area = np.maximum(inter_rect_x2 - inter_rect_x1, 0) * \
                 np.maximum(inter_rect_y2 - inter_rect_y1, 0)

    # Union Area
    b1_area = (b1_x2 - b1_x1) * (b1_y2 - b1_y1)
    b2_area = (b2_x2 - b2_x1) * (b2_y2 - b2_y1)
    
    iou = inter_area / (b1_area[:, None] + b2_area - inter_area + 1e-16)

    return iou

def linear_assignment(cost_matrix, thresh):
    if cost_matrix.size == 0:
        return np.empty((0, 2), dtype=int), tuple(range(cost_matrix.shape[0])), tuple(range(cost_matrix.shape[1]))
    
    matches, unmatched_a, unmatched_b = [], [], []
    
    # Use scipy linear_sum_assignment
    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    for i, j in zip(row_ind, col_ind):
        if cost_matrix[i, j] > thresh:
            unmatched_a.append(i)
            unmatched_b.append(j)
        else:
            matches.append((i, j))

    # Add unmatched rows and columns
    for i in range(cost_matrix.shape[0]):
        if i not in row_ind:
            unmatched_a.append(i)
            
    for j in range(cost_matrix.shape[1]):
        if j not in col_ind:
            unmatched_b.append(j)
            
    return matches, unmatched_a, unmatched_b
