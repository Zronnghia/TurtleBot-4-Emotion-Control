# Model MediaPipe Gesture Recognizer

`gesture_recognizer.task` – model chính thức của Google MediaPipe (bản float16, 8 373 440 byte,
SHA256 `97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482`), giấy phép Apache 2.0.

Gồm 3 mô hình nối tiếp: phát hiện lòng bàn tay → 21 landmark bàn tay → phân loại 7 cử chỉ
(`Closed_Fist, Open_Palm, Pointing_Up, Thumb_Down, Thumb_Up, Victory, ILoveYou`) + `None`.

Nguồn gốc / tải lại:
`https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task`
(xem https://ai.google.dev/edge/mediapipe/solutions/vision/gesture_recognizer).
Thiếu file này thì `gesture_recognition_node.py` tự tải về `~/.cache/tb4_lab04/models/`.

# Haar cascade phát hiện khuôn mặt (Bài 8)

`haarcascade_frontalface_default.xml` – bộ phát hiện mặt nhìn thẳng của OpenCV (Viola–Jones), 1254733 byte,
SHA256 `eeb6934b0cbf1e7b2b5ebea8fedc73ac653f0db5ffaa42e5ce61535830115466`. Giấy phép Intel License Agreement (kiểu BSD) – giữ nguyên trong phần đầu file.
Cùng nội dung với `cv2.data.haarcascades` của gói pip opencv-python; để sẵn trong repo vì OpenCV của apt,
conda và OpenCV 5 không có `cv2.data`. Dùng bởi `emotion_backends.FaceDetector` (tham số `cascade_path` để đổi file).
