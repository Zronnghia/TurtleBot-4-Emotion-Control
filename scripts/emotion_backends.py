#!/usr/bin/env python3
"""Bài 8 – phát hiện khuôn mặt + phân loại biểu cảm (DeepFace hoặc FER).

Luồng: khung BGR -> FaceDetector (Haar cascade của OpenCV, ảnh thu nhỏ cho nhanh) -> FaceTracker (làm mượt
khung mặt, chịu được vài khung bị trượt) -> backend phân loại 7 biểu cảm trên vùng mặt:

  deepface : DeepFace.analyze(actions=['emotion'], detector_backend='skip') – engine ONNX Runtime
             (nhẹ, ~2 ms/mặt trên CPU). Lần chạy ĐẦU tự tải trọng số 6 MB từ GitHub vào ~/.deepface/weights
             (install_emotion_deps.sh tải sẵn).
  fer      : FER (mini-Xception, trọng số đi kèm gói pip – không cần mạng) – cần TensorFlow.
  auto     : thử deepface, lỗi thì fer.

Hai backend đều dùng CHUNG bộ phát hiện mặt của repo (không dùng detector riêng của thư viện) -> khung mặt,
tốc độ và cách xử lý "không thấy mặt" giống nhau, so sánh được.
"""

import importlib.util
import os
import sys
import time
import types

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import emotion_logic as el  # noqa: E402

CASCADE_FILE = 'haarcascade_frontalface_default.xml'
BACKENDS = ('auto', 'deepface', 'fer')
INSTALL_HINT = ('Cài thư viện nhận diện biểu cảm (Ubuntu 22.04, pip3 --user, KHÔNG dùng conda):\n'
                '    bash scripts/install_emotion_deps.sh            # DeepFace + ONNX Runtime (khuyên dùng)\n'
                '    bash scripts/install_emotion_deps.sh --with-fer # thêm FER + TensorFlow')


# ------------------------------------------------------------------ hình học thuần (có unit test)
def iou(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    ix = max(0.0, min(ax + aw, bx + bw) - max(ax, bx))
    iy = max(0.0, min(ay + ah, by + bh) - max(ay, by))
    inter = ix * iy
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def expand_box(box, margin, width, height):
    """Nới khung mặt thêm margin (tỉ lệ) mỗi phía, cắt theo biên ảnh. Trả (x, y, w, h) nguyên."""
    x, y, w, h = box
    dx, dy = w * margin, h * margin
    x0, y0 = max(0, int(round(x - dx))), max(0, int(round(y - dy)))
    x1, y1 = min(width, int(round(x + w + dx))), min(height, int(round(y + h + dy)))
    return x0, y0, max(0, x1 - x0), max(0, y1 - y0)


class FaceTracker:
    """Chọn MỘT khuôn mặt (người điều khiển) và làm mượt khung qua các khung hình.

    - ưu tiên mặt trùng (IoU) với mặt đang theo; không có -> mặt lớn nhất;
    - Haar trượt vài khung (nghiêng đầu, mờ) -> giữ khung cũ tối đa hold_time giây thay vì báo mất mặt;
    - EMA vị trí khung (alpha) -> khung không rung."""

    def __init__(self, alpha=0.5, hold_time=0.3, min_iou=0.2):
        self.alpha = float(alpha)
        self.hold_time = float(hold_time)
        self.min_iou = float(min_iou)
        self.box = None
        self.last_seen = None

    def reset(self):
        self.box = None
        self.last_seen = None

    def update(self, t, boxes):
        """boxes: [(x, y, w, h)] hoặc [(x, y, w, h, điểm_tin_cậy)]. Trả (box hoặc None, là_khung_thật).

        Mặt mới: chọn điểm tin cậy cao nhất (Haar hay báo nhầm một vùng LỚN nhưng điểm thấp – chọn theo diện
        tích sẽ chọn nhầm), cùng điểm thì mặt lớn hơn."""
        cands = []
        for b in boxes or []:
            if len(b) >= 4 and b[2] > 0 and b[3] > 0:
                score = float(b[4]) if len(b) > 4 else 0.0
                cands.append((tuple(float(v) for v in b[:4]), score))
        if cands:
            pick = None
            if self.box is not None:
                best = max(cands, key=lambda c: iou(c[0], self.box))[0]
                if iou(best, self.box) >= self.min_iou:
                    pick = best
            if pick is None:
                pick = max(cands, key=lambda c: (c[1], c[0][2] * c[0][3]))[0]
                self.box = pick
            else:
                a = self.alpha
                self.box = tuple(a * n + (1 - a) * o for n, o in zip(pick, self.box))
            self.last_seen = t
            return self.box, True
        if self.box is not None and self.last_seen is not None and t - self.last_seen <= self.hold_time:
            return self.box, False
        self.reset()
        return None, False


# ------------------------------------------------------------------ vá tương thích
def _module_dir(name):
    spec = importlib.util.find_spec(name)
    if spec is None or not spec.origin:
        return None
    return os.path.dirname(spec.origin)


def install_compat_shims(cv2=None):
    """FER dùng `pkg_resources` (setuptools >= 81 đã bỏ) và `cv2.data` (không có ở OpenCV của apt / conda /
    OpenCV 5). Thiếu -> tạo bản thay thế tối thiểu, KHÔNG sửa gì trong thư viện đã cài."""
    try:
        import pkg_resources  # noqa: F401
    except ImportError:
        mod = types.ModuleType('pkg_resources')

        def resource_filename(package, path):
            base = _module_dir(package)
            return os.path.join(base or '', path)

        mod.resource_filename = resource_filename
        sys.modules['pkg_resources'] = mod
    if cv2 is not None and not hasattr(cv2, 'data'):
        d = _module_dir('fer')
        folder = os.path.join(d, 'data') if d else os.path.dirname(find_cascade(None) or '')
        cv2.data = types.SimpleNamespace(haarcascades=folder.rstrip('/') + '/')


def candidate_cascades(cv2=None, explicit=''):
    out = []
    if explicit:
        out.append(os.path.expanduser(explicit))
    try:
        import lab_common as lc
        for base in (lc.package_source_dir(), lc.package_share_dir()):
            if base:
                out.append(os.path.join(base, 'models', CASCADE_FILE))
    except Exception:  # noqa: BLE001
        pass
    here = os.path.dirname(os.path.realpath(__file__))
    out.append(os.path.join(os.path.dirname(here), 'models', CASCADE_FILE))
    if cv2 is not None and hasattr(cv2, 'data'):
        out.append(os.path.join(cv2.data.haarcascades, CASCADE_FILE))
    for p in ('/usr/share/opencv4/haarcascades', '/usr/share/opencv/haarcascades'):
        out.append(os.path.join(p, CASCADE_FILE))
    d = _module_dir('fer')
    if d:
        out.append(os.path.join(d, 'data', CASCADE_FILE))
    return out


def find_cascade(cv2=None, explicit=''):
    for p in candidate_cascades(cv2, explicit):
        if p and os.path.isfile(p):
            return p
    return None


# ------------------------------------------------------------------ phát hiện mặt
class FaceDetector:
    def __init__(self, cv2, cascade_path='', scale_factor=1.1, min_neighbors=5, min_face=60,
                 detect_width=320):
        self.cv2 = cv2
        path = find_cascade(cv2, cascade_path)
        if path is None:
            raise RuntimeError('Không tìm thấy {} (models/ của repo, cv2.data, /usr/share/opencv4)'.format(
                CASCADE_FILE))
        self.cascade = cv2.CascadeClassifier(path)
        if self.cascade.empty():
            raise RuntimeError('OpenCV không đọc được cascade {}'.format(path))
        self.path = path
        self.scale_factor = float(scale_factor)
        self.min_neighbors = int(min_neighbors)
        self.min_face = int(min_face)
        self.detect_width = int(detect_width)

    def detect(self, frame):
        """Trả danh sách (x, y, w, h, điểm) theo toạ độ ảnh gốc (điểm = levelWeight của Haar, càng cao càng
        chắc là mặt)."""
        cv2 = self.cv2
        gray = frame if frame.ndim == 2 else cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        s = 1.0
        if self.detect_width > 0 and w > self.detect_width:
            s = self.detect_width / float(w)
            gray = cv2.resize(gray, (self.detect_width, max(1, int(round(h * s)))),
                              interpolation=cv2.INTER_AREA)
        gray = cv2.equalizeHist(gray)
        mn = max(12, int(round(self.min_face * s)))
        try:
            faces, _, weights = self.cascade.detectMultiScale3(
                gray, scaleFactor=self.scale_factor, minNeighbors=self.min_neighbors, minSize=(mn, mn),
                outputRejectLevels=True)
            weights = [float(v) for v in (weights if len(weights) else [])]
        except Exception:  # noqa: BLE001 – OpenCV rất cũ: không có detectMultiScale3
            faces = self.cascade.detectMultiScale(gray, scaleFactor=self.scale_factor,
                                                  minNeighbors=self.min_neighbors, minSize=(mn, mn))
            weights = []
        faces = list(faces) if len(faces) else []
        if len(weights) != len(faces):
            weights = [0.0] * len(faces)
        return [(fx / s, fy / s, fw / s, fh / s, wt) for (fx, fy, fw, fh), wt in zip(faces, weights)]


# ------------------------------------------------------------------ phân loại biểu cảm
class DeepFaceBackend:
    name = 'deepface'

    def __init__(self, log=print, engine='onnx', margin=0.10):
        os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
        if engine and engine != 'auto' and 'DEEPFACE_BACKEND_ENGINE' not in os.environ:
            req = {'onnx': 'onnxruntime', 'tensorflow': 'tensorflow', 'pytorch': 'torch'}.get(engine)
            if req is None or importlib.util.find_spec(req) is not None:
                os.environ['DEEPFACE_BACKEND_ENGINE'] = engine
        from deepface import DeepFace
        self.DeepFace = DeepFace
        self.margin = float(margin)
        self.version = getattr(sys.modules.get('deepface'), '__version__', '?')
        self.engine = os.environ.get('DEEPFACE_BACKEND_ENGINE', 'mac dinh')
        self._silent = True
        import numpy as np
        log('DeepFace {} (engine {}): nạp mô hình emotion (lần đầu tải ~6 MB vào ~/.deepface/weights)...'.format(
            self.version, self.engine))
        self.predict(np.full((96, 96, 3), 128, dtype=np.uint8), (0, 0, 96, 96))   # nạp + chạy thử

    def predict(self, frame, box):
        h, w = frame.shape[:2]
        x, y, bw, bh = expand_box(box, self.margin, w, h)
        if bw < 8 or bh < 8:
            return None
        crop = frame[y:y + bh, x:x + bw]
        kw = dict(actions=['emotion'], detector_backend='skip', enforce_detection=False)
        if self._silent:
            try:
                res = self.DeepFace.analyze(crop, silent=True, **kw)
            except TypeError:          # bản DeepFace cũ không có tham số silent
                self._silent = False
                res = self.DeepFace.analyze(crop, **kw)
        else:
            res = self.DeepFace.analyze(crop, **kw)
        if isinstance(res, list):
            res = res[0] if res else {}
        return el.normalize_probs((res or {}).get('emotion'))


class FerBackend:
    name = 'fer'

    def __init__(self, log=print, use_tflite=True, cv2=None):
        os.environ.setdefault('TF_CPP_MIN_LOG_LEVEL', '2')
        import warnings
        # TF 2.19 báo tf.lite.Interpreter "deprecated", Keras 3 báo cấu trúc input – vô hại, chỉ làm rối log
        warnings.filterwarnings('ignore', category=UserWarning, module=r'(tensorflow|keras)(\.|$)')
        if cv2 is None:
            import cv2 as _cv2
            cv2 = _cv2
        install_compat_shims(cv2)
        try:
            from fer.fer import FER
        except ImportError:
            from fer import FER
        import numpy as np
        try:
            self.fer = FER(mtcnn=False, use_tflite=bool(use_tflite))
        except TypeError:              # bản FER 22.x không có use_tflite
            self.fer = FER(mtcnn=False)
        self.version = getattr(sys.modules.get('fer'), '__version__', '?')
        log('FER {}: mô hình mini-Xception (trọng số đi kèm gói pip)'.format(self.version))
        self.predict(np.full((120, 120, 3), 128, dtype=np.uint8), (12, 12, 96, 96))

    def predict(self, frame, box):
        x, y, w, h = [int(round(v)) for v in box]
        if w < 8 or h < 8:
            return None
        res = self.fer.detect_emotions(frame, face_rectangles=[(x, y, w, h)])
        if not res:
            return None
        return el.normalize_probs(res[0].get('emotions'))


def make_backend(name, log=print, deepface_engine='onnx', fer_tflite=True, cv2=None):
    """Tạo backend theo tên; 'auto' = deepface -> fer. Lỗi -> RuntimeError kèm hướng dẫn cài."""
    name = (name or 'auto').strip().lower()
    if name not in BACKENDS:
        raise RuntimeError('backend "{}" không hỗ trợ (chọn: {})'.format(name, ', '.join(BACKENDS)))
    order = ['deepface', 'fer'] if name == 'auto' else [name]
    errors = []
    for b in order:
        t0 = time.monotonic()
        try:
            if b == 'deepface':
                be = DeepFaceBackend(log, engine=deepface_engine)
            else:
                be = FerBackend(log, use_tflite=fer_tflite, cv2=cv2)
            log('Backend {} sẵn sàng sau {:.1f} s'.format(b, time.monotonic() - t0))
            return be
        except Exception as exc:  # noqa: BLE001
            errors.append('{}: {}: {}'.format(b, type(exc).__name__, exc))
            if name == 'auto':
                log('Không dùng được {} ({}: {})'.format(b, type(exc).__name__, exc))
    raise RuntimeError('Không khởi tạo được backend nhận diện biểu cảm:\n  ' + '\n  '.join(errors) +
                       '\n' + INSTALL_HINT)
