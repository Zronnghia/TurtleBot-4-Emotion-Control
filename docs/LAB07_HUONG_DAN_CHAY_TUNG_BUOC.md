# Bài 7 – Hướng dẫn chạy TỪNG BƯỚC (từ cài đặt đến nộp bài)

Phân vùng bản đồ + điều hướng TurtleBot 4 bằng giọng nói · Ubuntu 22.04 · ROS 2 Humble · Gazebo Fortress · Nav2

Làm lần lượt từ Bước 1 đến Bước 12. Mỗi bước có **"Kết quả đúng"** – chưa thấy đúng như vậy thì đừng sang bước sau,
xem mục **"Nếu lỗi"** ngay dưới bước đó hoặc [mục Xử lý sự cố](#xử-lý-sự-cố) ở cuối file.

Quy ước: workspace là `~/workspaces/tb4_gazebo` (giống các bài trước), thư mục package là
`~/workspaces/tb4_gazebo/src/tb4_lab04`. Dòng bắt đầu bằng `#` trong khung lệnh là chú thích, không cần gõ.

| Bước | Việc | Thời gian |
|---|---|---|
| 1 | Kiểm tra máy | 5 phút |
| 2 | Lấy code, build | 5 phút |
| 3 | Cài nhận dạng giọng nói | 5–10 phút |
| 4 | Chạy test | 1 phút |
| 5 | Phân vùng bản đồ | 2 phút |
| 6 | Kiểm tra micro + đo độ chính xác giọng nói | 10 phút |
| 7 | Chạy toàn bộ hệ thống | 3 phút |
| 8 | Ra lệnh bằng giọng nói (≥ 3 lệnh + khu vực không tồn tại) | 15 phút |
| 9 | Thử tránh vật cản | 5 phút |
| 10 | Quay video demo | 20 phút |
| 11 | Ảnh kết quả + báo cáo PDF | 10 phút |
| 12 | Đưa lên GitHub + checklist nộp bài | 10 phút |

---

## Bước 1 – Kiểm tra máy

```bash
lsb_release -d                      # Ubuntu 22.04.x
ls /opt/ros                         # humble
ign gazebo --versions               # 6.x (Fortress)
ros2 pkg list | grep -E "turtlebot4_ignition_bringup|nav2_bringup"
arecord -l                          # phải có ít nhất 1 "card" (micro)
```

**Kết quả đúng:** có `humble`, `6.x`, hai gói `turtlebot4_ignition_bringup` và `nav2_bringup`, và `arecord -l`
liệt kê micro.

**Nếu lỗi:**
- Thiếu ROS / Gazebo / TurtleBot 4: cài theo [`docs/LAB04_SLAM_README.md` mục 1](LAB04_SLAM_README.md#1-cài-đặt-làm-một-lần).
- Thiếu Nav2: `sudo apt install -y ros-humble-navigation2 ros-humble-nav2-bringup ros-humble-turtlebot4-navigation ros-humble-topic-tools`.
- `arecord -l` trống:
  - Máy ảo VirtualBox: *Devices → Audio → Audio Input* (bật).
  - VMware: *VM → Removable Devices → Sound card → Connect*.
  - WSL2: micro hay không dùng được → vẫn làm được bài bằng file WAV ghi trên Windows hoặc gõ lệnh (Bước 8.4).

Mở terminal mới thì luôn chạy (hoặc thêm vào cuối `~/.bashrc` một lần):

```bash
source /opt/ros/humble/setup.bash
source ~/workspaces/tb4_gazebo/install/setup.bash   # chỉ có sau Bước 2
export ROS_LOCALHOST_ONLY=1
```

Không bật conda: thấy `(base)` ở đầu dòng lệnh thì gõ `conda deactivate`.

---

## Bước 2 – Lấy code và build

**Cách A – từ file nén `tb4_lab07.tar.xz`** (giữ lại bản bài trước cho chắc):

```bash
cd ~/workspaces/tb4_gazebo/src
mv tb4_lab04 ~/tb4_lab04_bai6_backup 2>/dev/null     # cất bản cũ (nếu có)
tar -xJf ~/Downloads/tb4_lab07.tar.xz -C ~/workspaces/tb4_gazebo/src
ls tb4_lab04/scripts | grep voice                     # thấy voice_navigator.py, voice_command.py, voice_keyboard.py
```

**Cách B – từ GitHub:** `git clone https://github.com/<ten-ban>/<repo>.git ~/workspaces/tb4_gazebo/src/tb4_lab04`

Build:

```bash
cd ~/workspaces/tb4_gazebo
rm -rf build/tb4_lab04 install/tb4_lab04            # xoá bản build cũ của bài trước
source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select tb4_lab04
source install/setup.bash
```

**Kết quả đúng:** `Summary: 1 package finished`, và `ros2 pkg executables tb4_lab04 | grep voice` in ra
`voice_keyboard.py` và `voice_navigator.py`.

**Nếu lỗi:** `Package 'tb4_lab04' not found` → quên `source install/setup.bash` (mỗi terminal mới đều phải source).

---

## Bước 3 – Cài nhận dạng giọng nói

```bash
cd ~/workspaces/tb4_gazebo/src/tb4_lab04
bash scripts/install_voice_deps.sh            # Vosk + model tiếng Việt (32 MB) + sounddevice + espeak-ng
bash scripts/install_voice_deps.sh whisper    # (NÊN cài thêm) faster-whisper – chính xác hơn Vosk
```

Script cần `sudo` (cài `libportaudio2`, `espeak-ng`) và Internet. Ở cuối, script tự kiểm tra từng thành phần.

**Kết quả đúng:** các dòng `[PASS] numpy 1.x`, `[PASS] vosk + model tiếng Việt`, `[PASS] sounddevice (micro)`
(và `[PASS] faster-whisper` nếu cài whisper).

**Nếu lỗi:**

| Dòng lỗi | Cách xử lý |
|---|---|
| `[FAIL] numpy 1.x` | `pip3 install --user "numpy<2"` |
| `[FAIL] vosk + model` | xoá `~/.cache/tb4_lab04/vosk-model-small-vn-0.4*` rồi chạy lại script (tải dở) |
| `[FAIL] sounddevice (micro)` | xem Bước 1 phần micro |

Model Whisper `small` (~480 MB) được tải tự động ở **lần chạy đầu tiên** (Bước 6), nên lần đó cần Internet.

---

## Bước 4 – Chạy test

```bash
cd ~/workspaces/tb4_gazebo/src/tb4_lab04
python3 -m pytest test/ -q
```

**Kết quả đúng:**
- Đã `source` ROS (Bước 1): `203 passed`.
- Chưa source ROS: `192 passed, 11 skipped` – 11 test cần rclpy tự bỏ qua, như vậy cũng đúng.
- Không được có `failed` hay `error`.

**Nếu lỗi:**

| Lỗi | Nguyên nhân / cách xử lý |
|---|---|
| `ModuleNotFoundError: No module named '_pytest.scope'` (trong `anyio/pytest_plugin.py`) | pip đã kéo gói `anyio` mới về `~/.local` (khi cài faster-whisper…). Plugin pytest của nó cần pytest ≥ 7, còn Ubuntu 22.04 có pytest 6.2.5. File `pytest.ini` của repo đã chặn plugin này; bản cũ chưa có file đó thì chạy `python3 -m pytest test/ -q -p no:anyio` |
| `unknown hook 'pytest_launch_collect_makemodule'` / lỗi plugin `launch_testing` | đã chặn trong `pytest.ini`; hoặc chạy `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python3 -m pytest test/ -q` |
| `No module named pytest` | `sudo apt install -y python3-pytest` |
| pytest vẫn lỗi plugin khác | bỏ qua pytest, chạy thẳng bằng unittest: `python3 -m unittest discover -s test -p "test_*.py"` (kết quả đúng: `OK`) |

Không cần gỡ `anyio`: các gói khác (faster-whisper, httpx) cần nó.

---

## Bước 5 – Phân vùng bản đồ (yêu cầu 1 của đề)

```bash
ros2 run tb4_lab04 zone_segmentation.py
xdg-open ~/workspaces/tb4_gazebo/src/tb4_lab04/maps/map_zones.png
```

**Kết quả đúng:**
- Terminal in bảng **12 khu vực** A → L, cột cuối không có dòng `[LỖI]`.
- Ảnh có 12 vùng tô màu, mỗi vùng một chấm tròn (điểm đích của Nav2) và nhãn:
  A Phòng học, B Hành lang, F Sảnh chính (có dock), H Phòng hội nghị, I Phòng thí nghiệm, K Thư viện; các vùng còn lại
  là "Khu vực C/D/E/G/J/L".
- Ba file trong `maps/`, đúng là ba file phải nộp:
  - `zones.yaml`: thông tin khu vực.
  - `zones_labels.pgm`: ảnh nhãn.
  - `map_zones.png`: bản đồ phân vùng.

**Tuỳ chọn – đổi tên khu vực:** sửa `config/zone_names.yaml`. Mỗi mục gồm một điểm `anchor: [x, y]` nằm trong khu vực
(đọc toạ độ trên trục của `map_zones.png`) và một `name`. Chạy lại lệnh trên. Chọn tên **khác nhau rõ khi đọc lên**:
đừng đặt "phòng học" cạnh "phòng họp", vì nhận dạng giọng nói sẽ nhầm.

**Tuỳ chọn – vẽ vùng bằng tay:** `ros2 run tb4_lab04 zone_segmentation.py --manual config/zones_manual.yaml`
(file mẫu có 4 vùng). Nếu dùng cách này, bảng khu vực trong các bước sau sẽ khác.

---

## Bước 6 – Kiểm tra micro và đo độ chính xác nhận dạng giọng nói

Bước này cho bạn **số liệu thật** cho yêu cầu 2 và giúp chọn Vosk hay Whisper **trước** khi quay video.

**6.1. Micro thu được tiếng chưa?**

```bash
arecord -f S16_LE -r 16000 -c 1 -d 3 /tmp/thu.wav && aplay /tmp/thu.wav    # nói gì đó trong 3 s rồi nghe lại
ros2 run tb4_lab04 speech_recognizer_node.py --list-devices                # số thứ tự micro (cột có "> 0 in")
```

**6.2. Đo độ chính xác** – script hiện từng câu (10 câu trong `config/asr_test_sentences.yaml`). Bạn nhấn Enter rồi
đọc to, rõ, cách micro khoảng 30 cm:

```bash
ros2 run tb4_lab04 asr_benchmark.py --record --repeat 2                          # Vosk, mỗi câu đọc 2 lần
ros2 run tb4_lab04 asr_benchmark.py --dir ~/tb4_results/asr_<thời_gian> --engine whisper   # chấm lại CÙNG file bằng Whisper
ros2 run tb4_lab04 asr_benchmark.py --dir ~/tb4_results/asr_<thời_gian> --grammar          # Vosk + grammar
```

(`<thời_gian>` là thư mục lệnh đầu tiên in ra ở dòng `Đã lưu:`. Thêm `--device <số>` nếu micro không phải mặc định.)

**Kết quả đúng:** dòng tổng kết dạng
`ĐÚNG 17/20 (85 %) | BỎ (không nghe rõ) 1 | SAI (đứng yên) 2 | ĐI NHẦM 0`.

- **ĐI NHẦM phải bằng 0** (robot đi tới sai khu vực là lỗi nguy hiểm duy nhất).
- BỎ và SAI an toàn: robot đứng yên và bảo nói lại.
- Chọn engine có ĐÚNG cao nhất cho Bước 7. Ghi số này vào báo cáo (Bước 11).

**Nếu ĐÚNG thấp (< 60 %):**
- Thử `--engine whisper` (thường tốt hơn Vosk với tiếng Việt).
- Phòng yên tĩnh hơn, nói chậm, dùng tai nghe có micro.
- Với Vosk thử `--grammar`. Đổi lại, Vosk + grammar nghe "khu vực Z" thành "khu vực không rõ" – robot vẫn từ chối
  đúng, chỉ là câu báo kém cụ thể hơn.

Tham khảo (đo trong môi trường kiểm thử, **giọng máy espeak-ng + Whisper bản nhỏ nhất "base"**, không phải giọng
người): đúng 5/10, ĐI NHẦM 0.

**6.3. Vosk nghe kém thì đổi gì?** Chỉ cần ghi âm **một lần** (6.2). Sau đó chấm lại cùng bộ file bằng từng cách
dưới đây và chọn cách có ĐÚNG cao nhất mà ĐI NHẦM vẫn bằng 0. Xếp theo mức nên thử:

| # | Cách | Lệnh chấm (`D=~/tb4_results/asr_<thời_gian>`) | Dùng khi chạy (Bước 7) |
|---|---|---|---|
| 1 | **Whisper `small` trên CPU** – không cài thêm gì (ngoài `install_voice_deps.sh whisper`), ~1–3 s/câu | `ros2 run tb4_lab04 asr_benchmark.py --dir $D --engine whisper` | `asr_engine:=whisper` |
| 2 | **Whisper `medium` trên GPU NVIDIA** – chính xác nhất, ~0,5 s/câu; cần cài thư viện CUDA (bên dưới) | `ros2 run tb4_lab04 asr_benchmark.py --dir $D --engine whisper --whisper-model medium --whisper-device cuda` | `asr_engine:=whisper` + sửa `whisper_model: medium` trong `config/voice.yaml` |
| 3 | **Vosk + grammar** – nhanh, offline, chỉ nghe câu lệnh + tên khu vực | `ros2 run tb4_lab04 asr_benchmark.py --dir $D --grammar` | `use_grammar:=true` |

Với cách 3, phải xem kỹ câu "Đi đến khu vực Z" trong kết quả chấm. Grammar ép mọi âm thanh về các từ trong danh sách,
nên "Z" có thể bị ép thành một chữ có thật. Nếu dòng đó ra **ĐI NHẦM** thì **không** dùng cách 3.

**Cài thư viện CUDA cho Whisper (cách 2)** – chỉ làm nếu `nvidia-smi` chạy được và góc phải trên ghi
`CUDA Version: 12.x` trở lên:

```bash
pip3 install --user nvidia-cublas-cu12 "nvidia-cudnn-cu12==9.*" "numpy<2"
# thêm vào ~/.bashrc để mọi terminal đều có (mở terminal mới sau đó):
echo 'export LD_LIBRARY_PATH=$(python3 -c "import os,nvidia.cublas.lib,nvidia.cudnn.lib;print(os.path.dirname(nvidia.cublas.lib.__file__)+\":\"+os.path.dirname(nvidia.cudnn.lib.__file__))" 2>/dev/null):$LD_LIBRARY_PATH' >> ~/.bashrc
```

Kiểm tra: khi chạy, log có dòng `Whisper (faster-whisper, cuda)`. Nếu ra
`Whisper: không dùng được GPU (...) -> CPU` thì thư viện chưa đúng, nhưng hệ thống vẫn chạy bằng CPU, không bị dừng.
Model `medium` (~1,5 GB) được tải về ở lần chạy đầu. Nếu card chỉ có 4 GB VRAM thì đừng dùng `large-v3` khi Gazebo
đang chạy, vì hai bên tranh bộ nhớ.

**Đọc log thế nào?** Dòng `NGHE ĐƯỢC` có thể sai chính tả mà robot vẫn hiểu đúng. Ví dụ Vosk ra "đi biển khu vực à":
phần phân tích bỏ dấu ("à" thành "a") và bỏ qua từ thừa ("biển"), nên vẫn hiểu là khu vực A. Muốn biết robot hiểu
thành gì, xem dòng **`Câu lệnh: "…" -> navigate`** và **`Lộ trình: …`** ở terminal `voice_navigator`, đừng chỉ nhìn dòng
`NGHE ĐƯỢC`.

---

## Bước 7 – Chạy toàn bộ hệ thống

Chọn **một** trong hai cách.

**Cách 1 – một lệnh (đơn giản nhất):**

```bash
ros2 run tb4_lab04 kill_sim.sh                         # dọn phiên mô phỏng cũ (luôn chạy trước)
ros2 launch tb4_lab04 voice_nav.launch.py              # Vosk
# ros2 launch tb4_lab04 voice_nav.launch.py asr_engine:=whisper speak:=true   # Whisper + đọc phản hồi bằng loa
```

**Cách 2 – ba terminal (dễ nhìn khi quay video – khuyên dùng):**

```bash
# Terminal 1: Gazebo + TurtleBot 4 + AMCL + Nav2 + RViz2 (hiện khu vực, đường dự kiến)
ros2 run tb4_lab04 kill_sim.sh
ros2 launch tb4_lab04 navigation.launch.py rviz_config:=$(ros2 pkg prefix tb4_lab04)/share/tb4_lab04/rviz/voice.rviz

# Terminal 2: (đợi Terminal 1 có dòng "Managed nodes are active" lần thứ 2) – nhận dạng giọng nói + điều hướng
ros2 launch tb4_lab04 voice.launch.py                  # thêm asr_engine:=whisper nếu Bước 6 chọn Whisper

# Terminal 3: xem robot trả lời
ros2 topic echo /voice/feedback
```

**Kết quả đúng (đợi 1–3 phút):**
- Gazebo mở world `maze`, robot nằm trong dock.
- Terminal 1 có **hai lần** `Managed nodes are active` (localization, rồi navigation).
- RViz2 hiện bản đồ; trên đó có **đường viền màu + tên không dấu của 12 khu vực** ("Phong hoc (A)" …) và chấm điểm
  đích. Panel *Navigation 2* báo `Navigation: active`, `Localization: active`.
- Terminal của `voice_navigator` in `Sẵn sàng nhận lệnh. Các khu vực: Phòng học (A), …`.
- Terminal của `speech_recognizer` in `Đang nghe micro …`.

**Nếu lỗi:**

| Hiện tượng | Cách xử lý |
|---|---|
| Gazebo đen / đứng ở "loading" | Ctrl+C, `ros2 run tb4_lab04 kill_sim.sh`, chạy lại với `software_render:=true` |
| `spawn_objects` báo lỗi tải model (không có Internet) | thêm `spawn_objects:=false` |
| `Không có model Vosk` / `Chưa cài vosk` | làm lại Bước 3 |
| `Lỗi micro` | thêm `mic_device:=<số ở Bước 6.1>` |
| Robot trên RViz lệch khỏi bản đồ | dùng nút *2D Pose Estimate* đặt lại vị trí robot (như Bài 5) |

---

## Bước 8 – Ra lệnh bằng giọng nói (yêu cầu 2, 3, 4)

Nói từng câu dưới đây vào micro. Sau mỗi câu, chờ dòng `Hoàn thành lộ trình …` (hoặc câu trả lời) rồi mới nói câu
tiếp theo. Ở mỗi câu, xem ba nơi:
- Terminal speech: `NGHE ĐƯỢC: "…"`.
- Terminal navigator: `Câu lệnh … -> navigate`, `Lộ trình: …`, `Đã tới …`.
- RViz: đường **màu cam** = đường dự kiến, số **1, 2, 3** = thứ tự chặng, khu vực đang tới được tô đậm.

| # | Nói | Kết quả đúng |
|---|---|---|
| 8.1 | **"Đi đến khu vực G."** | `Lộ trình: Sảnh chính (F) -> Khu vực G` → `Robot đang ở dock – undock trước` → robot lùi ra, quay, chạy tới G → `Đã tới Khu vực G sau … s (sai số ~0.2 m)` |
| 8.2 | **"Đi đến khu vực Z."** | `Không có khu vực "khu vực z" trên bản đồ. Các khu vực hiện có: …` – **robot đứng yên** (yêu cầu 4) |
| 8.3 | **"Di chuyển từ sảnh chính đến khu vực C."** | Robot đang ở G nên: `Lộ trình: Khu vực G -> Sảnh chính (F) -> Khu vực C (robot đang ở Khu vực G nên tới Sảnh chính (F) trước)`; RViz vẽ đường cam qua F rồi tới C; robot đi F rồi C |
| 8.4 | **"Đi đến phòng thí nghiệm."** rồi khi robot đang chạy nói **"Dừng lại."** | Robot đi về phía khu vực I; sau "dừng lại": `Đã dừng theo lệnh.` – robot đứng yên ngay |
| 8.5 | **"Tôi đang ở đâu?"** | `Robot đang ở <khu vực>.` |
| 8.6 | **"Có những khu vực nào?"** | danh sách 12 khu vực |
| 8.7 (mở rộng) | **"Đi từ phòng học qua hành lang rồi đến thư viện."** | Lộ trình nhiều điểm A → B → K (đường dài, có thể "dừng lại" giữa chừng) |

**Nếu nói mà không có `NGHE ĐƯỢC`:**
- Kiểm tra micro (Bước 6.1). Với Whisper: nói rồi im lặng khoảng 1 s để node biết đã hết câu.
- Có dòng `BỎ QUA: "…" – …` nghĩa là bộ chặn đã loại một kết quả đáng ngờ. Hãy nói lại rõ hơn.

**Không có micro / micro kém – vẫn chạy được đầy đủ phần điều hướng.** Gõ câu thay cho nói (đi đúng đường như lệnh
nói):

```bash
ros2 run tb4_lab04 voice_keyboard.py          # gõ câu, Enter
```

Hoặc ghi âm trước thành file WAV rồi cho node nhận dạng đọc file (vẫn là nhận dạng giọng nói thật):

```bash
arecord -f S16_LE -r 16000 -c 1 -d 4 ~/lenh1.wav          # đọc "Đi đến khu vực G"
ros2 launch tb4_lab04 voice.launch.py wav_files:=$HOME/lenh1.wav
```

**Thử phân tích câu không cần mô phỏng:**

```bash
ros2 run tb4_lab04 voice_keyboard.py --check "đi tới khu vực Z" "Đi từ phòng học qua hành lang rồi đến thư viện"
```

---

## Bước 9 – Thử tránh vật cản (yêu cầu 3)

1. Nói **"Di chuyển từ khu vực G đến khu vực C."** (hoặc lệnh bất kỳ có đường đi qua vùng trống).
2. Trên RViz, khi đường cam hiện ra, chọn một điểm **trên đường cam**, cách robot và điểm đích hơn 1 m. Đọc toạ độ
   bằng nút *Publish Point* kết hợp `ros2 run tb4_lab04 goal_recorder.py`, hoặc dùng luôn điểm (2.2, 2.0) trên đường
   sảnh → C.
3. Ở terminal mới, thả hộp vào đó:

```bash
ros2 run tb4_lab04 drop_box.sh 2.2 2.0            # hộp đỏ 0.45 m, không có trên bản đồ
# xoá sau khi thử:  ros2 run tb4_lab04 drop_box.sh --remove hop1
```

**Kết quả đúng:** hộp đỏ xuất hiện trong Gazebo. Trên RViz, LiDAR thấy hộp (chấm đỏ) và local costmap tô vùng quanh
hộp. Robot **vòng qua** hộp rồi vẫn `Đã tới Khu vực C`. (Kết quả kiểm thử: quỹ đạo cách tâm hộp tối thiểu 0,72 m.)

---

## Bước 10 – Quay video demo

Phần mềm: `sudo apt install -y obs-studio` (hoặc `kazam`, `simplescreenrecorder`). **Bật thu âm micro** để người xem
nghe được câu lệnh.

Bố cục màn hình nên có: Gazebo (trái) + RViz (phải), các terminal speech / navigator nhỏ phía dưới.

Kịch bản khoảng 5–8 phút (đủ ý "nhận lệnh giọng nói → xác định đích → robot di chuyển"):

1. (15 s) Mở `maps/map_zones.png`, giới thiệu: bản đồ chia 12 khu vực, mỗi khu vực có tên và điểm đích.
2. (15 s) Mở `maps/zones.yaml`, chỉ một khu vực (id, name, goal).
3. Chạy hệ thống (Bước 7). Có thể tua nhanh đoạn khởi động.
4. Nói lần lượt các câu 8.1 → 8.5. Ở mỗi câu, cho thấy dòng `NGHE ĐƯỢC`, dòng `Lộ trình`, đường cam trên RViz, robot
   chạy trong Gazebo, và dòng `Đã tới`.
5. Bước 9: thả hộp, robot vòng tránh.
6. (tuỳ chọn) Câu 8.7 – nhiều điểm đến.

Upload lên Google Drive và đặt quyền **"Anyone with the link – Viewer"**.

---

## Bước 11 – Ảnh kết quả và báo cáo PDF (1–2 trang)

1. Khi tắt hệ thống (Ctrl+C), `voice_navigator` in ra `Kết quả: ~/tb4_results/voice_<thời_gian>/voice_run.json`.
   Vẽ quỹ đạo lên bản đồ phân vùng:

   ```bash
   ros2 run tb4_lab04 zone_segmentation.py --run ~/tb4_results/voice_<thời_gian>/voice_run.json
   cp ~/tb4_results/voice_<thời_gian>/voice_run.png ~/workspaces/tb4_gazebo/src/tb4_lab04/docs/report/fig_user/voice_run.png
   ```

2. Mở `docs/report_info.yaml` và điền:

   ```yaml
   ho_ten: "Họ Tên"
   link_video: "https://drive.google.com/..."
   link_github: "https://github.com/<ten-ban>/<repo>"
   voice_run: "~/tb4_results/voice_<thời_gian>/voice_run.json"   # bảng kết quả trong báo cáo lấy từ file này
   nhan_xet_bai7: "Đo độ chính xác nhận dạng (Bước 6): Whisper small đúng 17/20, đi nhầm 0; ..."   # số CỦA BẠN
   ```

3. Dựng báo cáo:

   ```bash
   cd ~/workspaces/tb4_gazebo/src/tb4_lab04
   python3 docs/report/build_report_bai7.py
   xdg-open docs/report/BaoCao_Bai7_TurtleBot4_Voice.pdf
   ```

**Kết quả đúng:** `Đã tạo: …BaoCao_Bai7_TurtleBot4_Voice.pdf (2 trang)`, **không** còn dòng `CẢNH BÁO: đang dùng
dữ liệu KIỂM THỬ` hay `CÒN THIẾU`. Báo cáo có:
- Hình 1: sơ đồ hệ thống.
- Hình 2: phương pháp phân vùng (distance transform + 12 khu vực).
- Mục nhận dạng giọng nói.
- Bảng kết quả các câu lệnh **của bạn**.
- Hình 3: quỹ đạo robot **của bạn**.

**Nếu lỗi:**
- `No module named reportlab` / `pypdf` → `pip3 install --user reportlab pypdf`.
- Báo cáo dài hơn 2 trang → rút ngắn `nhan_xet_bai7`.

---

## Bước 12 – Đưa lên GitHub (public) và checklist nộp bài

Tạo repo **Public** mới trên github.com (ví dụ `TurtleBot-4-Voice-Navigation`, không tick "Add README"), rồi:

```bash
cd ~/workspaces/tb4_gazebo/src/tb4_lab04
git checkout -b lab07
git add -A
git status                                  # kiểm tra: KHÔNG có build/, install/, log/, file .pt
git commit -m "Bài 7: phân vùng bản đồ + điều hướng TurtleBot 4 bằng giọng nói"
git remote add lab07 https://github.com/<ten-ban>/<repo>.git
git push -u lab07 lab07:main
```

GitHub hỏi mật khẩu thì dùng **Personal Access Token** (Settings → Developer settings → Tokens), không dùng mật khẩu
đăng nhập. Sau khi push: điền `link_github` (Bước 11) → dựng lại PDF → `git add -A && git commit -m "Báo cáo" && git push`.

**Checklist nộp bài:**

| Đề yêu cầu | Ở đâu | Đã có? |
|---|---|---|
| Source code trên GitHub (public) | repo ở trên – mở bằng trình duyệt **chưa đăng nhập** để chắc là public | ☐ |
| Bản đồ gốc | `maps/map.pgm`, `maps/map.yaml` | ☐ |
| Bản đồ phân vùng | `maps/map_zones.png` (+ `maps/zones_labels.pgm`) | ☐ |
| File thông tin khu vực | `maps/zones.yaml` (+ `config/zone_names.yaml`) | ☐ |
| ≥ 3 khu vực có nhãn, hiển thị trực quan | 12 khu vực – ảnh `map_zones.png` + RViz | ☐ |
| ≥ 3 câu lệnh giọng nói được nhận diện | video: 8.1, 8.3, 8.4 (+ số liệu Bước 6) | ☐ |
| Robot tự đi đúng khu vực, tránh vật cản bằng Nav2 | video: 8.1, 8.3, Bước 9 | ☐ |
| Xử lý khu vực không tồn tại | video: 8.2 | ☐ |
| Video demo nhận lệnh → xác định đích → di chuyển | link Google Drive (công khai) | ☐ |
| Báo cáo PDF 1–2 trang | `docs/report/BaoCao_Bai7_TurtleBot4_Voice.pdf` (dữ liệu của bạn) | ☐ |
| (mở rộng) nhiều điểm đến + đường đi dự kiến trên RViz | video: 8.3 / 8.7 | ☐ |

---

## Xử lý sự cố

| Hiện tượng | Nguyên nhân / cách xử lý |
|---|---|
| `Nav2 chưa sẵn sàng – đang chờ …` | nói lệnh khi Nav2 chưa lên xong: robot **tự chạy** khi Nav2 sẵn sàng (chờ tối đa 120 s, `nav2_wait` trong `config/voice.yaml`) |
| `Nav2 chưa sẵn sàng sau 120 s` | Nav2 không lên được: xem Terminal 1 có đủ 2 lần `Managed nodes are active` không; `ros2 action list \| grep navigate_to_pose` phải ra 1 dòng; Gazebo bị Force Quit thì chạy lại Bước 7 |
| Robot không rời dock, `Undock thất bại` | `ros2 run tb4_lab04 kill_sim.sh`, chạy lại; máy yếu thêm `software_render:=true` |
| `Không tới được … (ABORTED)` | thường do AMCL lệch: *2D Pose Estimate* trên RViz rồi nói lại; hoặc vật cản chắn kín đường |
| Nói "dừng lại" lúc robot đang undock mà robot vẫn lùi | đúng thiết kế: undock được làm nốt (~0,4 m) rồi robot mới đứng yên, nếu dừng giữa chừng robot sẽ kẹt trên mép dock |
| `NGHE ĐƯỢC` đúng nhưng `Không có khu vực …` | tên nói khác tên trong `zones.yaml` – thêm vào `aliases` trong `config/zone_names.yaml`, chạy lại Bước 5 |
| `BỎ QUA: … trùng nội dung initial_prompt` lặp lại nhiều | Whisper không nghe rõ – nói to/rõ hơn, hoặc `whisper_prompt: none` trong `config/voice.yaml` |
| Gazebo / Nav2 lỗi khác | [`docs/LAB05_NAV2_YOLO_README.md`](LAB05_NAV2_YOLO_README.md), [`docs/LAB04_SLAM_README.md`](LAB04_SLAM_README.md) |

Giải thích chi tiết thuật toán, tham số và kết quả kiểm thử: [`README.md`](LAB07_VOICE_README.md).
