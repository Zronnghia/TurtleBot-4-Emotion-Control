# Bài 8 – Hướng dẫn chạy TỪNG BƯỚC (từ cài đặt đến quay video)

Nhận diện biểu cảm khuôn mặt qua webcam và điều khiển TurtleBot 4 · Ubuntu 22.04 · ROS 2 Humble · Gazebo Fortress

Làm lần lượt từ Bước 1 đến Bước 9. Mỗi bước có **"Kết quả đúng"** – chưa thấy đúng như vậy thì đừng sang bước sau,
xem **"Nếu lỗi"** ngay dưới bước đó hoặc [README mục 7](README.md#7-xử-lý-sự-cố).

Quy ước: workspace `~/workspaces/tb4_gazebo` (như các bài trước), package ở `~/workspaces/tb4_gazebo/src/tb4_lab04`.
Dòng bắt đầu bằng `#` trong khung lệnh là chú thích.

| Bước | Việc | Thời gian |
|---|---|---|
| 1 | Kiểm tra máy + webcam | 5 phút |
| 2 | Lấy code, build | 5 phút |
| 3 | Cài DeepFace (và FER nếu muốn) | 5–15 phút |
| 4 | Chạy test | 1 phút |
| 5 | Thử nhận diện biểu cảm (chưa cần robot) | 5 phút |
| 6 | Thử robot bằng chuỗi biểu cảm giả (chưa cần webcam) | 10 phút |
| 7 | Chạy toàn bộ: webcam điều khiển robot | 10 phút |
| 8 | Quay video demo | 15 phút |
| 9 | Ảnh / số liệu kết quả | 5 phút |

---

## Bước 1 – Kiểm tra máy + webcam

```bash
lsb_release -d                 # Ubuntu 22.04.x
ls /opt/ros                    # humble
ign gazebo --versions          # 6.x (Fortress)
ls /dev/video*                 # phải có /dev/video0 (webcam laptop)
```

Mở terminal mới thì luôn chạy (hoặc thêm vào cuối `~/.bashrc` một lần):

```bash
source /opt/ros/humble/setup.bash
source ~/workspaces/tb4_gazebo/install/setup.bash   # chỉ có sau Bước 2
export ROS_LOCALHOST_ONLY=1
```

**Kết quả đúng:** có `humble`, `6.x`, có `/dev/video0`.

**Nếu lỗi:**
- Không có `/dev/video*`: máy ảo VirtualBox → *Devices → Webcams → (chọn webcam)*; VMware → *VM → Removable Devices →
  Camera → Connect*; WSL2 khó dùng webcam → nên chạy Ubuntu thật.
- Không bật conda: thấy `(base)` ở đầu dòng lệnh thì `conda deactivate`.

---

## Bước 2 – Lấy code, build

```bash
cd ~/workspaces/tb4_gazebo/src
# giải nén tb4_lab08.tar.xz vào đây (thay thế thư mục tb4_lab04 cũ) – hoặc git pull nếu dùng GitHub
cd ~/workspaces/tb4_gazebo
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select tb4_lab04
source install/setup.bash
ros2 pkg executables tb4_lab04 | grep emotion
```

**Kết quả đúng:** `Summary: 1 package finished`, và danh sách có `emotion_recognition_node.py`,
`emotion_behavior_node.py`, `emotion_sequence.py`.

**Nếu lỗi:** `Package 'tb4_lab04' not found` → quên `source install/setup.bash` ở terminal này.

---

## Bước 3 – Cài DeepFace (và FER nếu muốn)

```bash
cd ~/workspaces/tb4_gazebo/src/tb4_lab04
bash scripts/install_emotion_deps.sh               # DeepFace + ONNX Runtime (~60 MB) – đủ để làm bài
# bash scripts/install_emotion_deps.sh --with-fer  # thêm FER + TensorFlow CPU (~600 MB) – tuỳ chọn
```

Script hỏi mật khẩu `sudo` (cài `python3-pip`, `v4l-utils`), rồi cài bằng `pip --user`, tải sẵn trọng số DeepFace
(6 MB) và tự kiểm tra.

**Kết quả đúng** (cuối output):

```
[PASS] numpy: 1.26.4
[PASS] cv2 (có GUI): 4.10.0
[PASS] Haar cascade: .../models/haarcascade_frontalface_default.xml
[PASS] DeepFace: deepface 0.0.105 chạy được (7 lớp)
[PASS] MediaPipe (Bài 6) vẫn import được: 0.10.21      # hoặc [WARN] nếu chưa làm Bài 6 – không sao
KẾT QUẢ: TẤT CẢ OK
```

Dòng đỏ `ERROR: pip's dependency resolver ... deepface 0.0.105 requires retina-face ...` ở giữa là **bình thường**
(script cố ý không cài các gói nặng đó).

**Nếu lỗi:**
- `[FAIL] numpy: NumPy 2.x` → `pip3 install --user "numpy<2"` rồi chạy lại script.
- `[FAIL] cv2 (có GUI)` → `pip3 uninstall -y opencv-python-headless opencv-contrib-python-headless` rồi chạy lại script.
- `[FAIL] DeepFace ... ConnectionError / timed out` → máy không ra được github.com để tải trọng số: tải file
  `facial_expression_model_weights.onnx` (GitHub *serengil/deepface_models*, release *v1.0*) bằng máy khác, chép vào
  `~/.deepface/weights/`, chạy lại script. Hoặc dùng FER (`--with-fer`, trọng số có sẵn trong gói pip).

---

## Bước 4 – Chạy test

```bash
cd ~/workspaces/tb4_gazebo/src/tb4_lab04
python3 -m pytest test/ -q
```

**Kết quả đúng:** dòng cuối dạng `2xx passed, n skipped` và **không có** `failed`. Test cần FER/TensorFlow tự *skip* nếu
không cài `--with-fer` – vẫn đúng.

**Nếu lỗi:** `ModuleNotFoundError: No module named '_pytest.scope'` → repo đã có `pytest.ini` chặn plugin gây lỗi; kiểm
tra bạn đang đứng trong thư mục `tb4_lab04`.

---

## Bước 5 – Thử nhận diện biểu cảm (chưa cần robot)

```bash
ros2 run tb4_lab04 webcam_test.py                                  # (tuỳ chọn) xem webcam có hình + FPS, q để thoát
ros2 launch tb4_lab04 emotion.launch.py run_behavior:=false
```

Cửa sổ **Emotion Recognition - TurtleBot 4** hiện ra: bên trái ảnh webcam có khung quanh mặt + nhãn + %, bên phải bảng
*BIEU CAM ON DINH*, thanh xác suất 7 lớp, dòng `ROBOT (chua co emotion_behavior_node)`.

Lần lượt làm từng biểu cảm, **giữ mỗi biểu cảm ~2 s**:

| Biểu cảm | Cách làm cho dễ nhận |
|---|---|
| happy | cười rõ, thấy răng |
| sad | trề môi xuống, nhíu nhẹ hai đầu chân mày lên, cúi mắt |
| neutral | mặt thả lỏng, nhìn thẳng |
| angry | nhíu chặt chân mày xuống, mím môi / nghiến răng |
| surprise | nhướng mày cao, mở to mắt, há miệng chữ O |
| fear | mở to mắt, kéo khoé miệng sang ngang, hơi lùi đầu |

**Kết quả đúng:** log in `Biểu cảm ổn định: happy -> cong sang TRAI` … khi đổi biểu cảm, FPS ≥ 10 (góc trên trái).
Ghi lại biểu cảm nào khó nhận để biết khi quay video. Xem chi tiết số liệu: `ros2 topic echo /detected_emotion/info`.

**Nếu lỗi:**
- Không có khung mặt: đủ sáng (đèn trước mặt, không ngồi ngược sáng cửa sổ), nhìn thẳng, cách 0,5–1,5 m.
- Webcam USB: thêm `camera_source:=1`. Ảnh không lật như gương: `mirror:=false`.
- *fear* / *sad* luôn ra *surprise* / *neutral*: giới hạn của mô hình (README mục 8) – làm biểu cảm mạnh hơn, hoặc thử
  `backend:=fer` (nếu đã cài) xem mô hình nào hợp với mặt bạn hơn.
- Nhãn nhảy liên tục: `ros2 launch tb4_lab04 emotion.launch.py run_behavior:=false` rồi sửa `hold_time: 0.8` trong
  `config/emotion.yaml` (build `--symlink-install` nên sửa xong chạy lại là có hiệu lực).

Đóng: `Ctrl+C` (hoặc phím `q` trên cửa sổ).

---

## Bước 6 – Thử robot bằng chuỗi biểu cảm giả (chưa cần webcam)

Mục đích: chắc chắn robot + 6 quỹ đạo chạy đúng trước khi ghép webcam.

```bash
# Terminal 1 – Gazebo + node điều khiển (KHÔNG bật webcam)
ros2 launch tb4_lab04 emotion_demo.launch.py run_recognition:=false
```

Chờ log `Da ra giua san - san sang nhan bieu cam` (robot tự undock, chạy thẳng 1 m – ~30 s đến vài phút tuỳ máy).

```bash
# Terminal 2
ros2 run tb4_lab04 emotion_sequence.py --ros-args -p preset:=all
```

**Kết quả đúng:** Terminal 1 lần lượt in `>>> HAPPY -> cong sang TRAI`, `Hoan thanh quy dao happy`, rồi SAD, ANGRY,
SURPRISE, FEAR; trong Gazebo robot cong trái 90°, cong phải 90°, lùi nhẹ, xoay 1 vòng, tiến nhẹ. Cuối cùng
`SIGNAL_LOST ... MAT TIN HIEU - robot dung` (chuỗi đã hết – đúng thiết kế). Vẽ + đo:

```bash
ros2 run tb4_lab04 plot_emotion_run.py
```

Bảng phải gần: happy `quay° ≈ +90`, `trái(+) ≈ +0.30`; sad `≈ −90`, `≈ −0.30`; angry `tiến(+) ≈ −0.20`;
surprise `quay° ≈ 360`, `dời ≈ 0`; fear `tiến(+) ≈ +0.20`.

Thử thêm (tuỳ chọn): `-p preset:=interrupt` (neutral dừng giữa vòng xoay, biểu cảm mới ngắt quỹ đạo cũ).

**Nếu lỗi:**
- Robot không undock, log `Undock khong thanh cong` → `Ctrl+C`, `ros2 run tb4_lab04 kill_sim.sh`, chạy lại; vẫn lỗi:
  thêm `software_render:=true`.
- Gazebo đen / crash: `software_render:=true`.
- `VAT CAN cach ... m` → robot gần tường (chạy nhiều lần); khởi động lại mô phỏng.

Tắt Terminal 1 bằng `Ctrl+C`, rồi `ros2 run tb4_lab04 kill_sim.sh`.

---

## Bước 7 – Chạy toàn bộ: webcam điều khiển robot

```bash
# Terminal 1 – Gazebo
ros2 launch tb4_lab04 gesture_sim.launch.py
# Terminal 2 – khi Gazebo đã hiện robot (~30 s): webcam + điều khiển
ros2 launch tb4_lab04 emotion.launch.py window_position:=1000,0
```

(Một lệnh duy nhất cũng được: `ros2 launch tb4_lab04 emotion_demo.launch.py`.)

1. Giữ mặt **neutral** trong lúc robot undock (`ROBOT SETUP` trên cửa sổ). Chờ `ROBOT IDLE`.
2. **Cười** → robot cong sang trái (cửa sổ: `ROBOT EXECUTING`, `dang chay: happy 40%`).
3. Về **neutral** → (robot đã dừng sau quỹ đạo). **Buồn** → cong phải.
4. Neutral → **giận** → lùi nhẹ. Neutral → **ngạc nhiên** → xoay một vòng. Trong lúc xoay, về **neutral** → robot dừng
   ngay giữa vòng (chứng minh dừng được). Neutral → **sợ** → tiến nhẹ.
5. Rời khỏi camera khi robot đang chạy → robot dừng (`no_face`).

**Kết quả đúng:** mỗi lần đổi biểu cảm, sau ~0,5–0,7 s robot bắt đầu đúng quỹ đạo; giữ nguyên biểu cảm thì robot
không lặp lại (về neutral rồi làm lại mới chạy lại).

**Nếu lỗi:**
- Cửa sổ ghi đúng biểu cảm nhưng robot không chạy: xem dòng *ROBOT* – `SETUP` thì chờ undock; cùng biểu cảm vừa chạy
  → về neutral trước; `robot dang o dock` trong log → undock tay:
  `ros2 action send_goal /undock irobot_create_msgs/action/Undock "{}"`.
- Muốn giữ biểu cảm là robot chạy liên tục: `ros2 launch tb4_lab04 emotion.launch.py mode:=repeat`.
- Máy chậm (Gazebo + nhận diện cùng lúc): mỗi quỹ đạo có thể mất 10–30 s thời gian thực – cứ giữ/đổi biểu cảm theo
  trạng thái `EXECUTING`/`IDLE` trên cửa sổ, không theo đồng hồ.

---

## Bước 8 – Quay video demo

Dùng OBS (như Bài 7): *Sources → + → Screen Capture (XSHM)* (Wayland: đăng nhập phiên *Ubuntu on Xorg*). Sắp xếp
Gazebo bên trái, cửa sổ biểu cảm bên phải (`window_position:=1000,0`). Kịch bản ~2 phút:

1. (5 s) Giới thiệu: Bài 8, DeepFace + OpenCV, `/cmd_vel`.
2. (10 s) Terminal: `ros2 launch tb4_lab04 emotion.launch.py`, robot undock.
3. (90 s) Lần lượt 6 biểu cảm như Bước 7 – mỗi biểu cảm để người xem thấy rõ **nhãn trên cửa sổ** và **robot chuyển
   động** trong Gazebo. Có cảnh neutral dừng giữa vòng xoay.
4. (10 s) Rời camera → robot dừng; `Ctrl+C` → robot dừng hẳn.
5. (5 s) `ros2 run tb4_lab04 plot_emotion_run.py` → mở `trajectory.png`.

---

## Bước 9 – Ảnh / số liệu kết quả

```bash
ros2 run tb4_lab04 plot_emotion_run.py                 # lần chạy mới nhất
ls ~/tb4_results/emotion_*/                            # events.csv, odom.csv, summary.csv, trajectory.png
```

- `trajectory.png`: bên trái toàn bộ đường đi, bên phải từng quỹ đạo trong hệ toạ độ của robot (nét đứt = lý thuyết,
  nét liền = đo `/odom`).
- `summary.csv`: số đo từng quỹ đạo (thời gian mô phỏng, quãng đường, độ dời, góc quay, bán kính).
- Ảnh chụp cửa sổ nhận diện: `Print Screen` khi đang demo (hoặc `publish_image:=true` + `rqt_image_view /emotion/image`).
