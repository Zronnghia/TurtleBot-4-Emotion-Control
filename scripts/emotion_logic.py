#!/usr/bin/env python3
"""Bài 8 – phần logic THUẦN PYTHON (không cần ROS / OpenCV / TensorFlow) – có unit test.

  * chuẩn hoá kết quả của DeepFace / FER (7 lớp: angry, disgust, fear, happy, sad, surprise, neutral);
  * nhãn của một khung hình (ngưỡng độ tin cậy + khoảng cách với lớp thứ 2);
  * EmotionStabilizer: bỏ phiếu trong cửa sổ thời gian -> biểu cảm ỔN ĐỊNH (chống nhảy nhãn);
  * build_emotion_plan(): quỹ đạo cho từng biểu cảm (dùng Segment/SegmentRunner của Bài 6);
  * EmotionController: máy trạng thái quyết định khi nào bắt đầu / dừng quỹ đạo.

  Biểu cảm   Quỹ đạo (mặc định, sửa trong config/emotion.yaml)
  happy      cung tròn sang TRÁI   r = 0,30 m, quay 90°  (v = 0,15 m/s, ω = +0,5 rad/s)
  sad        cung tròn sang PHẢI   r = 0,30 m, quay 90°  (v = 0,15 m/s, ω = −0,5 rad/s)
  neutral    DỪNG tại chỗ (huỷ quỹ đạo đang chạy)
  angry      lùi nhẹ 0,20 m        (v = −0,10 m/s)
  surprise   xoay 1 vòng (360°) tại chỗ (ω = 1,0 rad/s)
  fear       tiến nhẹ 0,20 m       (v = 0,10 m/s)
  disgust    (đề bài không yêu cầu) -> không làm gì
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
from gesture_logic import Segment, plan_extent, to_ascii, as_bool, log_at  # noqa: E402,F401

EMOTIONS = ('angry', 'disgust', 'fear', 'happy', 'sad', 'surprise', 'neutral')
NO_FACE = 'no_face'          # không thấy khuôn mặt
UNKNOWN = 'unknown'          # có mặt nhưng mô hình không chắc chắn
ALL_LABELS = EMOTIONS + (NO_FACE, UNKNOWN)
ACTION_EMOTIONS = ('happy', 'sad', 'angry', 'surprise', 'fear')   # có quỹ đạo
STOP_EMOTION = 'neutral'

ALIASES = {
    'happiness': 'happy', 'joy': 'happy', 'smile': 'happy',
    'sadness': 'sad', 'anger': 'angry', 'mad': 'angry',
    'surprised': 'surprise', 'fearful': 'fear', 'scared': 'fear', 'afraid': 'fear',
    'disgusted': 'disgust', 'contempt': 'disgust', 'calm': 'neutral',
    'none': NO_FACE, 'noface': NO_FACE, 'no_face': NO_FACE, '': NO_FACE,
    'uncertain': UNKNOWN, 'unknown': UNKNOWN,
}

DISPLAY_VN = {
    'happy': 'Vui ve', 'sad': 'Buon', 'neutral': 'Binh thuong', 'angry': 'Tuc gian',
    'surprise': 'Ngac nhien', 'fear': 'So hai', 'disgust': 'Ghe so',
    NO_FACE: 'Khong thay mat', UNKNOWN: 'Khong chac',
}
ACTION_TEXT = {
    'happy': 'cong sang TRAI', 'sad': 'cong sang PHAI', 'neutral': 'DUNG tai cho',
    'angry': 'LUI nhe', 'surprise': 'XOAY 1 vong', 'fear': 'TIEN nhe',
    'disgust': '(khong co hanh vi)', NO_FACE: 'dung (khong thay mat)', UNKNOWN: '-',
}
COLORS = {  # BGR cho OpenCV
    'happy': (60, 200, 60), 'sad': (220, 120, 40), 'neutral': (200, 200, 200), 'angry': (40, 40, 230),
    'surprise': (0, 200, 255), 'fear': (200, 80, 200), 'disgust': (40, 140, 110),
    NO_FACE: (130, 130, 130), UNKNOWN: (160, 160, 160),
}


def canonical_emotion(name):
    """'Happy', 'HAPPINESS', ' happy ' -> 'happy'; lạ -> UNKNOWN; None/'' -> NO_FACE."""
    if name is None:
        return NO_FACE
    key = str(name).strip().lower().replace('-', '_').replace(' ', '_')
    if key in EMOTIONS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    return UNKNOWN


def parse_emotion_message(text):
    """Nội dung /detected_emotion: 'happy' hoặc JSON {"stable": "happy", ...} -> nhãn chuẩn."""
    text = (text or '').strip()
    if text.startswith('{'):
        import json
        try:
            data = json.loads(text)
            return canonical_emotion(data.get('stable', data.get('emotion')))
        except (ValueError, AttributeError):
            return UNKNOWN
    return canonical_emotion(text)


def normalize_probs(raw):
    """Kết quả backend -> dict 7 lớp, tổng = 1 (DeepFace trả %, FER trả 0..1, tên lớp có thể khác)."""
    out = {e: 0.0 for e in EMOTIONS}
    if not raw:
        return out
    for k, v in dict(raw).items():
        e = canonical_emotion(k)
        if e in out:
            try:
                fv = float(v)
            except (TypeError, ValueError):
                continue
            if math.isfinite(fv) and fv > 0:
                out[e] += fv
    total = sum(out.values())
    if total <= 0:
        return {e: 0.0 for e in EMOTIONS}
    return {e: v / total for e, v in out.items()}


def top_emotions(probs, n=2):
    return sorted(probs.items(), key=lambda kv: -kv[1])[:n]


def frame_label(probs, face_found, min_confidence=0.40, min_margin=0.10):
    """Nhãn của MỘT khung: không có mặt -> NO_FACE; lớp cao nhất < ngưỡng hoặc sát lớp thứ 2 -> UNKNOWN."""
    if not face_found:
        return NO_FACE, 0.0
    if not probs or sum(probs.values()) <= 0:
        return UNKNOWN, 0.0
    ranked = top_emotions(probs, 2)
    best, p1 = ranked[0]
    p2 = ranked[1][1] if len(ranked) > 1 else 0.0
    if p1 < min_confidence or p1 - p2 < min_margin:
        return UNKNOWN, p1
    return best, p1


class ProbSmoother:
    """Trung bình hàm mũ (EMA) xác suất qua các khung -> giảm rung nhãn. Mất mặt -> xoá."""

    def __init__(self, alpha=0.5):
        self.alpha = min(1.0, max(0.0, float(alpha)))
        self.value = None

    def reset(self):
        self.value = None

    def update(self, probs):
        if probs is None:
            self.value = None
            return None
        if self.value is None or self.alpha >= 1.0:
            self.value = dict(probs)
        else:
            a = self.alpha
            self.value = {e: a * probs.get(e, 0.0) + (1 - a) * self.value.get(e, 0.0) for e in EMOTIONS}
        return self.value


class EmotionStabilizer:
    """Biểu cảm ỔN ĐỊNH: nhãn L thay nhãn hiện tại khi trong hold(L) giây gần nhất
       * đã quan sát đủ lâu (khung cũ nhất trong cửa sổ cách hiện tại >= 80 % hold),
       * có >= min_frames khung mang nhãn L và tỉ lệ khung L >= vote_ratio.
    UNKNOWN (mô hình phân vân) không bao giờ thành nhãn ổn định: giữ nhãn cũ, chỉ không bỏ phiếu thêm.
    'neutral' và NO_FACE có hold riêng (ngắn) để robot DỪNG nhanh."""

    def __init__(self, hold_time=0.6, hold_overrides=None, vote_ratio=0.6, min_frames=3,
                 priority=(STOP_EMOTION, NO_FACE)):
        self.hold_time = float(hold_time)
        self.hold_overrides = dict(hold_overrides or {})
        self.vote_ratio = float(vote_ratio)
        self.min_frames = max(1, int(min_frames))
        self.priority = tuple(priority)
        self.history = []
        self.stable = NO_FACE
        self.stable_since = None
        self.stable_ratio = 0.0

    def hold(self, label):
        return float(self.hold_overrides.get(label, self.hold_time))

    def reset(self):
        self.history = []
        self.stable = NO_FACE
        self.stable_since = None
        self.stable_ratio = 0.0

    def _ratio(self, label, t):
        h = self.hold(label)
        window = [(ft, lb) for ft, lb in self.history if t - ft <= h + 1e-9]
        if not window or t - window[0][0] < 0.8 * h - 1e-9:
            return None
        n = sum(1 for _, lb in window if lb == label)
        r = n / float(len(window))
        return r if (n >= self.min_frames and r >= self.vote_ratio) else None

    def update(self, t, label):
        """Thêm nhãn khung tại thời điểm t (s). Trả (nhãn_ổn_định, có_đổi)."""
        label = canonical_emotion(label)
        self.history.append((float(t), label))
        horizon = max([self.hold_time] + list(self.hold_overrides.values())) + 0.5
        self.history = [(ft, lb) for ft, lb in self.history if t - ft <= horizon]
        cands = {}
        for lb in set(lb for _, lb in self.history):
            if lb == UNKNOWN:
                continue
            r = self._ratio(lb, t)
            if r is not None:
                cands[lb] = r
        if not cands:                             # chưa nhãn nào đủ phiếu -> giữ nhãn cũ
            self.stable_ratio = 0.0
            return self.stable, False
        ranked = sorted(cands, key=lambda lb: (self.priority.index(lb) if lb in self.priority
                                               else len(self.priority), -cands[lb]))
        winner = ranked[0]
        if self.stable in cands and winner not in self.priority and self.stable not in self.priority:
            winner = self.stable                  # vẫn đạt -> giữ (tránh lật qua lại giữa 2 lớp)
        changed = winner != self.stable
        if changed:
            self.stable = winner
            self.stable_since = t
        self.stable_ratio = cands.get(self.stable, 0.0)
        return self.stable, changed


# ----------------------------------------------------------------------------------------------------
# Quỹ đạo
# ----------------------------------------------------------------------------------------------------
DEFAULT_EMOTION_PARAMS = {
    'arc_speed': 0.15,          # m/s – happy / sad
    'arc_radius': 0.30,         # m
    'arc_angle': 90.0,          # độ quay trên cung (90° = 1/4 vòng)
    'back_distance': 0.20,      # m – angry
    'back_speed': 0.10,         # m/s
    'forward_distance': 0.20,   # m – fear
    'forward_speed': 0.10,      # m/s
    'spin_speed': 1.0,          # rad/s – surprise
    'spin_turns': 1.0,          # số vòng
}


def _pos(p, key, minimum):
    v = abs(float(p[key]))
    if v < minimum:
        raise ValueError('{} = {} quá nhỏ (>= {})'.format(key, p[key], minimum))
    return v


def build_emotion_plan(emotion, params=None):
    """Danh sách Segment cho biểu cảm. neutral -> [] (dừng). disgust/không có mặt/lạ -> None (không làm gì)."""
    p = dict(DEFAULT_EMOTION_PARAMS)
    p.update(params or {})
    e = canonical_emotion(emotion)
    if e == STOP_EMOTION:
        return []
    if e in ('happy', 'sad'):
        v = _pos(p, 'arc_speed', 0.02)
        r = _pos(p, 'arc_radius', 0.05)
        ang = math.radians(_pos(p, 'arc_angle', 5.0))
        w = v / r
        side = 'trai' if e == 'happy' else 'phai'
        return [Segment('{}: cung sang {} r={:.2f} m'.format(e, side, r), v, w if e == 'happy' else -w,
                        ang, 'angle')]
    if e == 'angry':
        return [Segment('angry: lui {:.2f} m'.format(abs(float(p['back_distance']))),
                        -_pos(p, 'back_speed', 0.02), 0.0, _pos(p, 'back_distance', 0.01), 'dist')]
    if e == 'fear':
        return [Segment('fear: tien {:.2f} m'.format(abs(float(p['forward_distance']))),
                        _pos(p, 'forward_speed', 0.02), 0.0, _pos(p, 'forward_distance', 0.01), 'dist')]
    if e == 'surprise':
        turns = _pos(p, 'spin_turns', 0.05)
        return [Segment('surprise: xoay {:.0f} deg'.format(360.0 * turns), 0.0, _pos(p, 'spin_speed', 0.1),
                        2.0 * math.pi * turns, 'angle')]
    return None


def describe_plans(params=None):
    """Mô tả ngắn từng quỹ đạo (log khi khởi động + README)."""
    lines = []
    for e in ('happy', 'sad', 'neutral', 'angry', 'surprise', 'fear'):
        try:
            plan = build_emotion_plan(e, params)
        except ValueError as exc:
            lines.append('  {:<9}-> THAM SO SAI: {}'.format(e, exc))
            continue
        if not plan:
            lines.append('  {:<9}-> {}'.format(e, ACTION_TEXT[e]))
            continue
        r, end = plan_extent(plan)
        lines.append('  {:<9}-> {:<15} ~{:.1f} s, cuoi cach diem dau {:.2f} m, quay {:+.0f} deg'.format(
            e, ACTION_TEXT[e], sum(s.nominal_duration() for s in plan), math.hypot(end[0], end[1]),
            math.degrees(end[2])))
    return lines


# ----------------------------------------------------------------------------------------------------
# Máy trạng thái
# ----------------------------------------------------------------------------------------------------
WAITING = 'WAITING'           # chưa nhận /detected_emotion nào
SETUP = 'SETUP'               # đang rời dock / ra giữa sân (bỏ qua biểu cảm)
IDLE = 'IDLE'                 # đứng yên, sẵn sàng
EXECUTING = 'EXECUTING'       # đang chạy quỹ đạo của một biểu cảm
SIGNAL_LOST = 'SIGNAL_LOST'   # mất /detected_emotion quá signal_timeout


class EmotionController:
    """Quyết định hành động theo biểu cảm ổn định (nhận MỖI khung từ node nhận diện).

    Quy tắc (theo thứ tự ưu tiên):
      1. 'neutral' -> DỪNG ngay (huỷ quỹ đạo đang chạy).
      2. Không thấy mặt (no_face) và stop_on_no_face -> DỪNG (người điều khiển rời camera).
      3. Biểu cảm có quỹ đạo, KHÁC biểu cảm vừa kích hoạt -> chạy quỹ đạo mới (ngắt quỹ đạo cũ).
      4. Cùng biểu cảm vẫn giữ: mode 'once' -> không lặp lại (muốn chạy lại: đổi sang biểu cảm khác, vd
         neutral, rồi quay lại); mode 'repeat' -> chạy lại sau khi xong + repeat_delay.
      5. 'unknown' (mô hình phân vân) và 'disgust' -> không đổi gì.
    Mỗi lần kích hoạt cách nhau ít nhất min_interval (chống bị kích hoạt dồn dập khi nhãn rung).
    Mất tín hiệu > signal_timeout -> DỪNG, chờ tín hiệu trở lại.
    """

    def __init__(self, mode='once', signal_timeout=1.0, stop_on_no_face=True, repeat_delay=1.0,
                 min_interval=0.5):
        if mode not in ('once', 'repeat'):
            raise ValueError("mode phải là 'once' hoặc 'repeat'")
        self.mode = mode
        self.signal_timeout = float(signal_timeout)
        self.stop_on_no_face = as_bool(stop_on_no_face)
        self.repeat_delay = float(repeat_delay)
        self.min_interval = float(min_interval)
        self.state = WAITING
        self.active = None           # biểu cảm đang chạy quỹ đạo
        self.last_trigger = None     # biểu cảm kích hoạt gần nhất (để không lặp lại khi giữ nguyên)
        self.last_trigger_t = -1e9
        self.last_done_t = None
        self.emotion = NO_FACE       # biểu cảm ổn định mới nhất nhận được
        self.last_msg_t = None
        self.message = 'Cho tin hieu bieu cam...'
        self.count = {}

    # ---- chuẩn bị (undock)
    def begin_setup(self, text='Dang chuan bi...'):
        self.state = SETUP
        self.message = text

    def end_setup(self, ok, text=''):
        if self.state == SETUP:
            self.state = IDLE if self.last_msg_t is not None else WAITING
        self.message = text or ('San sang' if ok else 'Chuan bi loi')
        self.last_trigger = None     # biểu cảm đang giữ trong lúc chuẩn bị sẽ được thực hiện ngay

    # ---- sự kiện
    def on_message(self, label, t):
        label = canonical_emotion(label)
        self.last_msg_t = t
        self.emotion = label
        acts = []
        if self.state == SETUP:
            return acts
        if self.state in (WAITING, SIGNAL_LOST):
            acts.append(('info', 'Nhan tin hieu bieu cam' + (' tro lai' if self.state == SIGNAL_LOST else '')))
            self.state = IDLE
            self.message = 'San sang'
        if label == STOP_EMOTION:
            self.last_trigger = STOP_EMOTION
            if self.state == EXECUTING:
                acts += self._stop('neutral -> dung tai cho')
            return acts
        if label == NO_FACE:
            self.last_trigger = None
            if self.state == EXECUTING and self.stop_on_no_face:
                acts += self._stop('khong thay khuon mat')
            return acts
        if label not in ACTION_EMOTIONS:     # unknown / disgust
            return acts
        if t - self.last_trigger_t < self.min_interval:
            return acts
        if label != self.last_trigger:
            return acts + self._start(label, t)
        if (self.mode == 'repeat' and self.state == IDLE and self.last_done_t is not None
                and t - self.last_done_t >= self.repeat_delay):
            return acts + self._start(label, t)
        return acts

    def tick(self, t):
        if self.state in (WAITING, SETUP, SIGNAL_LOST) or self.last_msg_t is None:
            return []
        if t - self.last_msg_t > self.signal_timeout:
            acts = []
            if self.state == EXECUTING:
                acts.append(('stop', 'mat tin hieu bieu cam > {:.1f} s'.format(self.signal_timeout)))
            self.state = SIGNAL_LOST
            self.active = None
            self.last_trigger = None
            self.message = 'MAT TIN HIEU - robot dung'
            return acts
        return []

    def on_finished(self, ok, reason='', t=None):
        """Quỹ đạo kết thúc (xong / lỗi / vật cản)."""
        name = self.active
        if self.state == EXECUTING:
            self.state = IDLE
        self.active = None
        self.last_done_t = t
        if ok:
            self.count[name] = self.count.get(name, 0) + 1
            self.message = 'Xong {} ({})'.format(name, ACTION_TEXT.get(name, ''))
            return [('info', 'Hoan thanh quy dao {}'.format(name))]
        self.message = 'Dung {}: {}'.format(name, reason)
        return [('stop', reason)]

    # ---- nội bộ
    def _start(self, label, t):
        self.last_trigger = label
        self.last_trigger_t = t
        prev = self.active
        self.state = EXECUTING
        self.active = label
        self.message = '{} -> {}'.format(label, ACTION_TEXT[label])
        return [('start', label, prev)]

    def _stop(self, reason):
        self.state = IDLE
        self.active = None
        self.message = 'DUNG: {}'.format(reason)
        return [('stop', reason)]

    def describe(self):
        return {'state': self.state, 'emotion': self.emotion, 'active': self.active, 'mode': self.mode,
                'message': self.message, 'count': dict(self.count)}
