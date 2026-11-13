# Hướng dẫn nhanh – Bài 7: phân vùng bản đồ + điều hướng bằng giọng nói

Từng bước có kết quả mong đợi: [`HUONG_DAN_CHAY_TUNG_BUOC.md`](LAB07_HUONG_DAN_CHAY_TUNG_BUOC.md). Giải thích chi tiết: [`README.md`](LAB07_VOICE_README.md). Workspace giả định `~/workspaces/tb4_gazebo`.

## 0. Cài (1 lần) và build

```bash
cd ~/workspaces/tb4_gazebo && source /opt/ros/humble/setup.bash
colcon build --symlink-install --packages-select tb4_lab04 && source install/setup.bash
export ROS_LOCALHOST_ONLY=1
cd src/tb4_lab04 && bash scripts/install_voice_deps.sh     # Vosk + model tiếng Việt + sounddevice
python3 -m pytest test/ -q                                 # tất cả phải PASSED
```

## 1. Phân vùng bản đồ

```bash
ros2 run tb4_lab04 zone_segmentation.py        # -> maps/zones.yaml, maps/zones_labels.pgm, maps/map_zones.png
# đổi tên: sửa config/zone_names.yaml rồi chạy lại; vẽ tay: --manual config/zones_manual.yaml
```

## 2. Chạy

```bash
ros2 run tb4_lab04 kill_sim.sh
ros2 launch tb4_lab04 voice_nav.launch.py      # Gazebo + Nav2 + RViz2 + nhận dạng giọng nói + điều hướng
#   asr_engine:=whisper | use_asr:=false (gõ lệnh) | speak:=true | software_render:=true
```

Không có micro: `ros2 run tb4_lab04 voice_keyboard.py` rồi gõ câu lệnh.
Đo độ chính xác nhận dạng trên giọng bạn: `ros2 run tb4_lab04 asr_benchmark.py --record`.
Thả vật cản thử tránh: `ros2 run tb4_lab04 drop_box.sh 2.2 2.0`.

## 3. Câu lệnh mẫu (chờ `Hoàn thành lộ trình` rồi nói câu tiếp)

1. "Đi đến khu vực G"
2. "Đi đến khu vực Z"  → bị từ chối, robot đứng yên
3. "Di chuyển từ sảnh chính đến khu vực C"  → đi qua sảnh (F) trước
4. "Đi đến phòng thí nghiệm"  (khu vực H giờ tên "Phòng hội nghị")
5. "Dừng lại" (giữa chừng) · "Có những khu vực nào?" · "Tôi đang ở đâu?"

## 4. Kết quả, báo cáo, nộp

```bash
ros2 run tb4_lab04 zone_segmentation.py --run ~/tb4_results/voice_<thời_gian>/voice_run.json   # ảnh quỹ đạo
python3 docs/report/build_report_bai7.py       # điền link trong docs/report_info.yaml trước
git add -A && git commit -m "Bài 7" && git push
```
