# Hướng dẫn nhanh – Bài 8: biểu cảm khuôn mặt điều khiển TurtleBot 4

Từng bước có kết quả mong đợi: [`HUONG_DAN_CHAY_TUNG_BUOC.md`](HUONG_DAN_CHAY_TUNG_BUOC.md). Giải thích chi tiết: [`README.md`](README.md). Workspace giả định `~/workspaces/tb4_gazebo`.

## 0. Cài (1 lần) và build

```bash
cd ~/workspaces/tb4_gazebo && source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select tb4_lab04 && source install/setup.bash
export ROS_LOCALHOST_ONLY=1
cd src/tb4_lab04 && bash scripts/install_emotion_deps.sh   # DeepFace + ONNX Runtime (--with-fer: thêm FER)
python3 -m pytest test/ -q                                 # không có "failed"
```

## 1. Chỉ nhận diện (không robot)

```bash
ros2 launch tb4_lab04 emotion.launch.py run_behavior:=false            # backend:=fer  camera_source:=1
ros2 topic echo /detected_emotion                                      # happy | sad | neutral | angry | surprise | fear | no_face
```

## 2. Robot + chuỗi biểu cảm giả (không webcam)

```bash
ros2 launch tb4_lab04 emotion_demo.launch.py run_recognition:=false    # T1, chờ "san sang nhan bieu cam"
ros2 run tb4_lab04 emotion_sequence.py --ros-args -p preset:=all       # T2 (interrupt | hold | lost)
ros2 run tb4_lab04 plot_emotion_run.py                                 # bảng số đo + trajectory.png
```

## 3. Demo đầy đủ

```bash
ros2 launch tb4_lab04 gesture_sim.launch.py                            # T1: Gazebo (sân trống)
ros2 launch tb4_lab04 emotion.launch.py window_position:=1000,0        # T2: webcam + robot
# hoặc 1 lệnh: ros2 launch tb4_lab04 emotion_demo.launch.py
```

| Biểu cảm | Robot |
|---|---|
| happy | cong trái 90° (r 0,3 m) |
| sad | cong phải 90° |
| neutral | dừng ngay |
| angry | lùi 0,2 m |
| surprise | xoay 360° |
| fear | tiến 0,2 m |
| không thấy mặt / mất tín hiệu 1 s | dừng |

Mỗi lần biểu cảm ĐỔI chạy 1 quỹ đạo (về neutral rồi làm lại để lặp); `mode:=repeat` để lặp khi còn giữ.
Tắt: `Ctrl+C`, rồi `ros2 run tb4_lab04 kill_sim.sh`.
