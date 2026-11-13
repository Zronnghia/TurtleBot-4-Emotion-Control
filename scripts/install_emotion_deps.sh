#!/usr/bin/env bash
# Bài 8 – cài thư viện nhận diện biểu cảm khuôn mặt trên Ubuntu 22.04 + ROS 2 Humble (pip --user).
#
#   bash scripts/install_emotion_deps.sh              # DeepFace + ONNX Runtime (mặc định, ~60 MB)
#   bash scripts/install_emotion_deps.sh --with-fer   # thêm FER + TensorFlow CPU (~600 MB)
#   (chạy lại nhiều lần vẫn an toàn)
#
# Vì sao KHÔNG chạy thẳng `pip install deepface` / `pip install fer` (đã kiểm thử trên Python 3.10):
#   * deepface kéo opencv-contrib-python-HEADLESS -> cửa sổ OpenCV (cv2.imshow) của Bài 6/8 hỏng; còn kéo
#     retina-face -> TensorFlow (~600 MB) dù ta chỉ cần ONNX Runtime.
#   * fer kéo facenet-pytorch -> PyTorch (~2 GB), moviepy, ffmpeg – không cần cho webcam.
#   * bản mới của các gói đó có thể kéo NumPy 2.x -> cv_bridge (apt, NumPy 1.x) hỏng.
# => cài deepface / fer với --no-deps rồi cài ĐÚNG các phụ thuộc cần dùng, ghim numpy<2, protobuf<5
#    (MediaPipe 0.10.21 của Bài 6 cần protobuf 4.x), OpenCV 4.10 có GUI.
# Phiên bản đã kiểm thử cùng nhau: numpy 1.26.4, opencv-python 4.10.0.84, deepface 0.0.105,
#   onnxruntime 1.23.2, fer 25.10.3, tensorflow-cpu 2.19.1, mediapipe 0.10.21 (vẫn chạy).
# `pip check` sẽ báo "deepface requires ... which is not installed" – BÌNH THƯỜNG (cố ý không cài).
set -u

say(){ printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
die(){ printf '\033[1;31m[LỖI]\033[0m %s\n' "$*"; exit 1; }
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WITH_FER=0
for a in "$@"; do
  case "$a" in
    --with-fer) WITH_FER=1 ;;
    -h|--help) sed -n '2,20p' "$0"; exit 0 ;;
    *) die "tham số lạ: $a" ;;
  esac
done
DEEPFACE_VERSION="${DEEPFACE_VERSION:-0.0.105}"
FER_VERSION="${FER_VERSION:-25.10.3}"
TF_VERSION="${TF_VERSION:-2.19.1}"
PY="${PY:-/usr/bin/python3}"          # PY=... để thử trong venv
PIP_USER="--user"
[ -n "${VIRTUAL_ENV:-}" ] && PIP_USER=""

say "0. Kiểm tra môi trường"
if [ -n "${CONDA_DEFAULT_ENV:-}" ]; then
  die "Đang trong conda ($CONDA_DEFAULT_ENV). Chạy 'conda deactivate' rồi mở terminal mới."
fi
[ -x "$PY" ] || die "Không thấy $PY"
"$PY" --version
[ -f /opt/ros/humble/setup.bash ] || echo "CẢNH BÁO: không thấy /opt/ros/humble – vẫn cài thư viện Python."
PIP=("$PY" -m pip install $PIP_USER)
CONS="$(mktemp)"
trap 'rm -f "$CONS"' EXIT
printf 'numpy<2\nprotobuf<5\nopencv-python<4.11\nopencv-contrib-python<4.11\n' > "$CONS"

if command -v apt-get >/dev/null 2>&1 && [ -z "${SKIP_APT:-}" ]; then
  say "1. Gói apt (cần sudo): pip, v4l-utils (dò webcam), matplotlib"
  sudo apt-get update -y && sudo apt-get install -y python3-pip v4l-utils python3-matplotlib python3-yaml \
    || die "apt thất bại"
fi

say "2. NumPy 1.x + OpenCV 4.10 (có GUI)"
"${PIP[@]}" -c "$CONS" "numpy<2" "opencv-python<4.11" || die "pip install thất bại (cần Internet tới pypi.org)"

say "3. DeepFace ${DEEPFACE_VERSION} (--no-deps) + ONNX Runtime"
echo "(Dòng \"ERROR: pip's dependency resolver ... deepface requires ...\" nếu có là BÌNH THƯỜNG – cố ý không cài các gói đó)"
"${PIP[@]}" --no-deps "deepface==${DEEPFACE_VERSION}" || die "không cài được deepface"
"${PIP[@]}" -c "$CONS" "onnxruntime>=1.16,<1.24" requests gdown tqdm || die "không cài được onnxruntime"

if [ "$WITH_FER" = 1 ]; then
  say "4. FER ${FER_VERSION} (--no-deps) + TensorFlow CPU ${TF_VERSION}"
  "${PIP[@]}" --no-deps "fer==${FER_VERSION}" || die "không cài được fer"
  "${PIP[@]}" -c "$CONS" "tensorflow-cpu==${TF_VERSION}" requests || die "không cài được tensorflow-cpu"
fi

# gói khác lỡ kéo opencv-python-headless -> cv2.imshow không mở được cửa sổ
if "$PY" -m pip show opencv-python-headless >/dev/null 2>&1 || "$PY" -m pip show opencv-contrib-python-headless >/dev/null 2>&1; then
  say "Gỡ OpenCV headless (làm hỏng cửa sổ hiển thị)"
  "$PY" -m pip uninstall -y opencv-python-headless opencv-contrib-python-headless
  "${PIP[@]}" --force-reinstall --no-deps "opencv-python<4.11"
  if "$PY" -m pip show opencv-contrib-python >/dev/null 2>&1; then
    "${PIP[@]}" --force-reinstall --no-deps "opencv-contrib-python<4.11"
  fi
fi

say "5. Tải sẵn trọng số DeepFace (~6 MB -> ~/.deepface/weights) + kiểm tra"
DEEPFACE_BACKEND_ENGINE=onnx TF_CPP_MIN_LOG_LEVEL=2 "$PY" - "$HERE" "$WITH_FER" <<'PYEOF'
import os, sys
sys.path.insert(0, sys.argv[1])
with_fer = sys.argv[2] == "1"
ok = True
def chk(name, fn, required=True):
    global ok
    try:
        print("[PASS] {}: {}".format(name, fn()))
    except Exception as e:
        if required:
            ok = False
        print("[{}] {}: {}: {}".format("FAIL" if required else "WARN", name, type(e).__name__, e))
import numpy
def np_ver():
    if not numpy.__version__.startswith("1."):
        raise RuntimeError("NumPy {} (cần 1.x cho cv_bridge của Humble)".format(numpy.__version__))
    return numpy.__version__
chk("numpy", np_ver)
def cv():
    import cv2
    gui = [l.strip() for l in cv2.getBuildInformation().splitlines() if l.strip().startswith(("GTK", "QT"))]
    if not any("YES" in g for g in gui):
        raise RuntimeError("OpenCV {} KHÔNG có GUI (bản headless?)".format(cv2.__version__))
    return cv2.__version__
chk("cv2 (có GUI)", cv)
import cv2
import emotion_backends as eb
chk("Haar cascade", lambda: eb.FaceDetector(cv2).path)
def run(name):
    b = eb.make_backend(name, log=lambda m: None, cv2=cv2)
    img = numpy.full((240, 240, 3), 128, numpy.uint8)
    p = b.predict(img, (60, 60, 120, 120))
    return "{} {} chạy được ({} lớp)".format(b.name, getattr(b, "version", ""), len(p))
chk("DeepFace", lambda: run("deepface"))
if with_fer:
    chk("FER", lambda: run("fer"))
chk("MediaPipe (Bài 6) vẫn import được", lambda: __import__("mediapipe").__version__, required=False)
print("\nKẾT QUẢ: {}".format("TẤT CẢ OK" if ok else "CÓ LỖI – xem [FAIL] ở trên"))
sys.exit(0 if ok else 1)
PYEOF
rc=$?
echo
echo "Ghi chú: 'pip check' báo deepface/fer thiếu retina-face, facenet-pytorch, moviepy... là CỐ Ý (không cần)."
[ $rc -eq 0 ] && echo "Tiếp theo: cd ~/ros2_ws && colcon build --packages-select tb4_lab04 --symlink-install"
exit $rc
