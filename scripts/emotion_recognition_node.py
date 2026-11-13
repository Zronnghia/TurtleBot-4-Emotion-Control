#!/usr/bin/env python3
"""Bài 8 – node nhận diện BIỂU CẢM KHUÔN MẶT từ webcam (DeepFace hoặc FER + OpenCV).

  ros2 run tb4_lab04 emotion_recognition_node.py
  ros2 launch tb4_lab04 emotion.launch.py                                   # + emotion_behavior_node
  ros2 run tb4_lab04 emotion_recognition_node.py --ros-args -p backend:=fer
  ros2 run tb4_lab04 emotion_recognition_node.py --ros-args -p camera_source:=~/thu.mp4

Mỗi khung hình:
  webcam (luồng đọc riêng, luôn lấy khung mới nhất) -> lật gương -> phát hiện mặt (Haar, ảnh thu nhỏ 320 px)
  -> FaceTracker (giữ đúng 1 người, làm mượt khung) -> backend phân loại 7 biểu cảm trên vùng mặt
  -> ProbSmoother (EMA xác suất) -> nhãn khung (ngưỡng min_confidence / min_margin, không chắc -> unknown)
  -> EmotionStabilizer (bỏ phiếu theo thời gian) -> biểu cảm ỔN ĐỊNH
  -> publish /detected_emotion (std_msgs/String) MỖI khung (cũng là "nhịp tim" cho watchdog của robot)
  -> cửa sổ OpenCV: khung mặt + nhãn + xác suất 7 lớp + biểu cảm ổn định + hành động + trạng thái robot + FPS.

Topic:
  pub /detected_emotion        std_msgs/String  'happy'|'sad'|'neutral'|'angry'|'surprise'|'fear'|'disgust'|
                                                'no_face'  (nhãn ổn định)
  pub /detected_emotion/info   std_msgs/String  JSON: raw, conf, probs, box, stable, vote, fps, backend
  pub /emotion/image           sensor_msgs/Image (bgr8, chỉ khi publish_image:=true – xem trên rqt/RViz)
  sub /emotion_behavior/state  std_msgs/String  JSON trạng thái robot (vẽ lên cửa sổ)
Không có camera / hết video -> KHÔNG publish -> emotion_behavior_node mất tín hiệu -> robot dừng.
Phím q / Esc trên cửa sổ: đóng node.
"""

import json
import os
import signal
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import emotion_logic as el  # noqa: E402
import gesture_recognition_node as grn  # noqa: E402  (FrameSource, tiện ích cửa sổ – dùng chung với Bài 6)

WINDOW = 'Emotion Recognition - TurtleBot 4'
PANEL_W = 270
ORDER = ('happy', 'sad', 'neutral', 'angry', 'surprise', 'fear', 'disgust')


# ------------------------------------------------------------------ vẽ
def draw_view(cv2, frame, box, real_box, raw, conf, probs, stable, vote, fps, backend, robot,
              source_ok=True):
    """Ghép khung camera + bảng bên phải. Trả ảnh mới (h x (w + PANEL_W))."""
    import numpy as np
    h, w = frame.shape[:2]
    canvas = np.zeros((h, w + PANEL_W, 3), dtype=np.uint8)
    canvas[:, :w] = frame
    canvas[:, w:] = (32, 32, 32)
    font = cv2.FONT_HERSHEY_SIMPLEX
    aa = cv2.LINE_AA
    if box is not None:
        x, y, bw, bh = [int(round(v)) for v in box]
        col = el.COLORS.get(raw, (200, 200, 200))
        cv2.rectangle(canvas, (x, y), (x + bw, y + bh), col, 2 if real_box else 1, aa)
        text = '{} {:.0f}%'.format(raw, 100 * conf) if raw not in (el.NO_FACE,) else raw
        (tw, th), _ = cv2.getTextSize(text, font, 0.6, 2)
        ty = y - 8 if y - 8 - th > 0 else y + bh + th + 8
        cv2.rectangle(canvas, (x, ty - th - 6), (x + tw + 8, ty + 4), col, -1)
        cv2.putText(canvas, text, (x + 4, ty), font, 0.6, (0, 0, 0), 2, aa)
    if not source_ok:
        cv2.putText(canvas, 'KHONG CO CAMERA - robot se dung', (20, h // 2), font, 0.7, (0, 0, 255), 2, aa)
    # thanh trên: FPS + backend
    cv2.rectangle(canvas, (0, 0), (w, 26), (0, 0, 0), -1)
    cv2.putText(canvas, 'FPS {:4.1f}  backend: {}'.format(fps, backend), (8, 18), font, 0.5,
                (255, 255, 255), 1, aa)
    # bảng phải
    px = w + 12
    cv2.putText(canvas, 'BIEU CAM ON DINH', (px, 24), font, 0.5, (200, 200, 200), 1, aa)
    scol = el.COLORS.get(stable, (200, 200, 200))
    cv2.putText(canvas, stable.upper(), (px, 56), font, 0.85, scol, 2, aa)
    cv2.putText(canvas, el.DISPLAY_VN.get(stable, ''), (px, 78), font, 0.5, scol, 1, aa)
    cv2.putText(canvas, '-> ' + el.ACTION_TEXT.get(stable, ''), (px, 100), font, 0.5, (255, 255, 255), 1, aa)
    cv2.putText(canvas, 'phieu {:.0f}%'.format(100 * vote), (px + 160, 78), font, 0.4, (160, 160, 160), 1, aa)
    y0 = 128
    cv2.putText(canvas, 'Xac suat (khung hien tai)', (px, y0), font, 0.45, (200, 200, 200), 1, aa)
    bar_w = PANEL_W - 110
    for i, e in enumerate(ORDER):
        yy = y0 + 18 + i * 24
        p = float((probs or {}).get(e, 0.0))
        cv2.putText(canvas, e, (px, yy + 12), font, 0.45, (230, 230, 230), 1, aa)
        cv2.rectangle(canvas, (px + 70, yy), (px + 70 + bar_w, yy + 14), (70, 70, 70), -1)
        cv2.rectangle(canvas, (px + 70, yy), (px + 70 + int(bar_w * p), yy + 14), el.COLORS.get(e), -1)
        cv2.putText(canvas, '{:3.0f}'.format(100 * p), (px + 74 + bar_w, yy + 12), font, 0.4,
                    (230, 230, 230), 1, aa)
    yr = y0 + 18 + len(ORDER) * 24 + 16
    cv2.putText(canvas, 'ROBOT', (px, yr), font, 0.5, (200, 200, 200), 1, aa)
    if robot:
        st = robot.get('state', '?')
        colr = {'EXECUTING': (60, 220, 60), 'SIGNAL_LOST': (60, 60, 255), 'SETUP': (0, 200, 255)}.get(
            st, (230, 230, 230))
        cv2.putText(canvas, st, (px + 60, yr), font, 0.5, colr, 2, aa)
        act = robot.get('active')
        prog = robot.get('progress')
        line = 'dang chay: {}'.format(act) if act else 'dung yen'
        if act and prog is not None:
            line += ' {:.0f}%'.format(100 * prog)
        cv2.putText(canvas, line, (px, yr + 20), font, 0.45, (230, 230, 230), 1, aa)
        msg = el.to_ascii(robot.get('message', ''))
        for k in range(0, min(len(msg), 96), 32):
            cv2.putText(canvas, msg[k:k + 32], (px, yr + 40 + (k // 32) * 16), font, 0.4, (180, 180, 180), 1, aa)
    else:
        cv2.putText(canvas, '(chua co emotion_behavior_node)', (px, yr + 20), font, 0.4, (150, 150, 150), 1, aa)
    # chú giải
    leg = ['happy->cong trai  sad->cong phai', 'neutral->dung  angry->lui nhe',
           'surprise->xoay 1 vong  fear->tien nhe']
    for i, t in enumerate(leg):
        cv2.putText(canvas, t, (px, h - 52 + 16 * i), font, 0.37, (150, 150, 150), 1, aa)
    return canvas


def display_available(env=None):
    """Có màn hình để mở cửa sổ không? OpenCV (Qt) ABORT cả tiến trình nếu không kết nối được X -> kiểm
    tra trước: không có DISPLAY/WAYLAND_DISPLAY, hoặc DISPLAY cục bộ ':N' mà không có socket X -> False."""
    env = os.environ if env is None else env
    if env.get('WAYLAND_DISPLAY'):
        return True
    disp = env.get('DISPLAY', '')
    if not disp:
        return False
    if disp.startswith(':'):
        num = disp[1:].split('.')[0]
        if num.isdigit():
            return os.path.exists('/tmp/.X11-unix/X' + num)
    return True                # DISPLAY từ xa (ssh -X: localhost:10.0) – để OpenCV tự thử


_WIN = {'seen_visible': False}


def show(cv2, img):
    """Hiển thị; True nếu người dùng bấm q/Esc hoặc đóng cửa sổ."""
    cv2.imshow(WINDOW, img)
    key = cv2.waitKey(1) & 0xFF
    if key in (27, ord('q')):
        return True
    try:
        visible = cv2.getWindowProperty(WINDOW, cv2.WND_PROP_VISIBLE)
    except Exception:  # noqa: BLE001
        return False
    if visible >= 1:
        _WIN['seen_visible'] = True
        return False
    return _WIN['seen_visible']


# ------------------------------------------------------------------ main
def main(argv=None):
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.signals import SignalHandlerOptions
    from sensor_msgs.msg import Image
    from std_msgs.msg import String

    rclpy.init(args=argv, signal_handler_options=SignalHandlerOptions.NO)
    node = Node('emotion_recognition_node')
    log = node.get_logger()
    stop = {'flag': False, 'count': 0}

    def on_signal(signum, frame):
        stop['count'] += 1
        stop['flag'] = True
        if stop['count'] >= 2:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    from rcl_interfaces.msg import ParameterDescriptor

    def P(name, default):
        node.declare_parameter(name, default, ParameterDescriptor(dynamic_typing=True))
        value = node.get_parameter(name).value
        return default if value is None else value

    prm = {
        'camera_source': str(P('camera_source', '0')),
        'frame_width': int(P('frame_width', 640)),
        'frame_height': int(P('frame_height', 480)),
        'camera_fps': int(P('camera_fps', 30)),
        'camera_fourcc': str(P('camera_fourcc', '')),
        'mirror': el.as_bool(P('mirror', True)),
        'loop': el.as_bool(P('loop', False)),
        'image_hold': float(P('image_hold', 3.0)),
        'max_fps': float(P('max_fps', 30.0)),
        'backend': str(P('backend', 'deepface')),
        'deepface_engine': str(P('deepface_engine', 'onnx')),
        'fer_tflite': el.as_bool(P('fer_tflite', True)),
        'cascade_path': str(P('cascade_path', '')),
        'detect_width': int(P('detect_width', 320)),
        'min_face': int(P('min_face', 60)),
        'min_neighbors': int(P('min_neighbors', 5)),
        'face_hold_time': float(P('face_hold_time', 0.3)),
        'face_alpha': float(P('face_alpha', 0.5)),
        'prob_alpha': float(P('prob_alpha', 0.5)),
        'min_confidence': float(P('min_confidence', 0.40)),
        'min_margin': float(P('min_margin', 0.10)),
        'hold_time': float(P('hold_time', 0.6)),
        'neutral_hold_time': float(P('neutral_hold_time', 0.4)),
        'no_face_hold_time': float(P('no_face_hold_time', 0.5)),
        'vote_ratio': float(P('vote_ratio', 0.6)),
        'min_frames': int(P('min_frames', 3)),
        'show_window': el.as_bool(P('show_window', True)),
        'window_scale': float(P('window_scale', 1.0)),
        'window_position': str(P('window_position', '')),
        'publish_image': el.as_bool(P('publish_image', False)),
        'emotion_topic': str(P('emotion_topic', '/detected_emotion')),
        'state_topic': str(P('state_topic', '/emotion_behavior/state')),
        'log_changes': el.as_bool(P('log_changes', True)),
    }

    def fatal(msg):
        log.fatal(msg)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
        return 1

    try:
        import cv2
        import numpy  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        return fatal('Không import được OpenCV/NumPy: {}'.format(exc))
    grn.fix_qt_fonts()
    import emotion_backends as eb
    try:
        detector = eb.FaceDetector(cv2, prm['cascade_path'], min_neighbors=prm['min_neighbors'],
                                   min_face=prm['min_face'], detect_width=prm['detect_width'])
    except Exception as exc:  # noqa: BLE001
        return fatal('Bộ phát hiện mặt: {}'.format(exc))
    log.info('Phát hiện mặt: Haar cascade {}'.format(detector.path))
    try:
        backend = eb.make_backend(prm['backend'], log=lambda m: log.info(m),
                                  deepface_engine=prm['deepface_engine'], fer_tflite=prm['fer_tflite'], cv2=cv2)
    except Exception as exc:  # noqa: BLE001
        return fatal(str(exc))
    backend_name = '{} {}'.format(backend.name, getattr(backend, 'version', ''))

    pub = node.create_publisher(String, prm['emotion_topic'], 10)
    pub_info = node.create_publisher(String, prm['emotion_topic'] + '/info', 10)
    pub_img = node.create_publisher(Image, '/emotion/image', 2) if prm['publish_image'] else None
    robot = {'state': None, 't': 0.0}

    def on_state(msg):
        try:
            robot['state'] = json.loads(msg.data)
            robot['t'] = time.monotonic()
        except ValueError:
            pass

    node.create_subscription(String, prm['state_topic'], on_state, 10)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    spin_thread = threading.Thread(target=lambda: grn._spin(executor, stop), daemon=True)
    spin_thread.start()

    source = grn.FrameSource(cv2, grn.parse_camera_source(prm['camera_source']), prm['frame_width'],
                             prm['frame_height'], prm['camera_fps'], prm['loop'], prm['image_hold'],
                             lambda lv, m: el.log_at(log, lv, m), prm['camera_fourcc'])
    exit_code = 0
    try:
        source.start()
    except Exception as exc:  # noqa: BLE001
        log.fatal(str(exc))
        stop['flag'] = True
        exit_code = 1

    tracker = eb.FaceTracker(alpha=prm['face_alpha'], hold_time=prm['face_hold_time'])
    smoother = el.ProbSmoother(prm['prob_alpha'])
    stab = el.EmotionStabilizer(
        hold_time=prm['hold_time'],
        hold_overrides={el.STOP_EMOTION: prm['neutral_hold_time'], el.NO_FACE: prm['no_face_hold_time']},
        vote_ratio=prm['vote_ratio'], min_frames=prm['min_frames'])

    showing = prm['show_window']
    if showing and not display_available():
        log.warn('Không có màn hình (DISPLAY={!r}) – chạy KHÔNG hiển thị cửa sổ. Chạy trong terminal của máy có '
                 'giao diện, hoặc show_window:=false.'.format(os.environ.get('DISPLAY', '')))
        showing = False
    if showing:
        try:
            cv2.namedWindow(WINDOW, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(WINDOW, int((prm['frame_width'] + PANEL_W) * prm['window_scale']),
                             int(prm['frame_height'] * prm['window_scale']))
            pos = grn.parse_window_position(prm['window_position'])
            if pos is not None:
                cv2.moveWindow(WINDOW, pos[0], pos[1])
        except Exception as exc:  # noqa: BLE001
            log.warn('Không mở được cửa sổ OpenCV ({}) – chạy không hiển thị. Nếu dùng '
                     'opencv-python-headless: pip3 uninstall -y opencv-python-headless'.format(exc))
            showing = False

    log.info('Đang nhận diện biểu cảm -> {} (Ctrl+C để dừng)\n{}'.format(
        prm['emotion_topic'], '\n'.join(el.describe_plans())))
    fps = 0.0
    last_frame_t = None
    min_period = 1.0 / prm['max_fps'] if prm['max_fps'] > 0 else 0.0
    last_proc = 0.0
    frames = 0
    errors = 0
    last_report = time.monotonic()
    placeholder = None
    t_infer = 0.0
    try:
        while not stop['flag'] and rclpy.ok():
            frame = source.read(timeout=0.25)
            now = time.monotonic()
            rstate = robot['state'] if now - robot['t'] < 2.0 else None
            if frame is None:
                if source.kind != 'camera' and source.finished:
                    log.info('Hết nguồn ảnh/video -> dừng node (robot sẽ dừng do mất tín hiệu)')
                    break
                if showing:
                    if placeholder is None:
                        placeholder = grn.numpy_zeros(cv2, prm['frame_height'], prm['frame_width'])
                    view = draw_view(cv2, placeholder, None, False, el.NO_FACE, 0.0, None, '-', 0.0, 0.0,
                                     backend_name, rstate, source_ok=False)
                    if show(cv2, view):
                        break
                continue
            if min_period and now - last_proc < 0.8 * min_period:
                continue
            last_proc = now
            try:
                if frame.ndim == 2:
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                elif frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                if prm['mirror']:
                    frame = cv2.flip(frame, 1)
                ti = time.monotonic()
                box, real = tracker.update(now, detector.detect(frame))
                probs = None
                if box is not None:
                    p = backend.predict(frame, box)
                    probs = smoother.update(p) if p is not None else smoother.value
                else:
                    smoother.reset()
                t_infer = 0.9 * t_infer + 0.1 * (time.monotonic() - ti) if t_infer else time.monotonic() - ti
                errors = 0
            except Exception as exc:  # noqa: BLE001 – 1 khung lỗi không làm chết node
                errors += 1
                log.error('Lỗi xử lý khung hình ({}/10): {}: {}'.format(errors, type(exc).__name__, exc))
                if errors >= 10:
                    log.fatal('10 khung liên tiếp lỗi -> dừng node (robot sẽ dừng do mất tín hiệu)')
                    exit_code = 1
                    break
                continue
            raw, conf = el.frame_label(probs, box is not None, prm['min_confidence'], prm['min_margin'])
            stable, changed = stab.update(now, raw)
            pub.publish(String(data=stable))
            info = {'raw': raw, 'conf': round(conf, 3), 'stable': stable, 'vote': round(stab.stable_ratio, 2),
                    'fps': round(fps, 1), 'infer_ms': round(1000 * t_infer, 1), 'backend': backend.name,
                    'box': [int(v) for v in box] if box is not None else None,
                    'probs': {k: round(v, 3) for k, v in (probs or {}).items()}}
            pub_info.publish(String(data=json.dumps(info)))
            if changed and prm['log_changes']:
                log.info('Biểu cảm ổn định: {:<9} -> {}   (khung: {} {:.0f}%)'.format(
                    stable, el.ACTION_TEXT.get(stable, ''), raw, 100 * conf))
            frames += 1
            if last_frame_t is not None and now > last_frame_t:
                inst = 1.0 / (now - last_frame_t)
                fps = 0.9 * fps + 0.1 * inst if fps > 0 else inst
            last_frame_t = now
            if now - last_report >= 30.0:
                last_report = now
                el.log_at(log, 'warn' if 0 < fps < 8.0 else 'info', 'FPS {:.1f}, xử lý {:.0f} ms/khung – đang '
                          'publish: {}'.format(fps, 1000 * t_infer, stable))
            if showing or pub_img is not None:
                view = draw_view(cv2, frame, box, real, raw, conf, probs, stable, stab.stable_ratio, fps,
                                 backend_name, rstate)
                if pub_img is not None:
                    pub_img.publish(grn.image_msg_from_bgr(view, node.get_clock().now().to_msg(), 'webcam',
                                                           Image))
                if showing and show(cv2, view):
                    break
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        log.error('Lỗi trong vòng lặp nhận diện: {}: {}'.format(type(exc).__name__, exc))
        exit_code = 1
    finally:
        stop['flag'] = True
        source.stop()
        if showing:
            try:
                cv2.destroyAllWindows()
                cv2.waitKey(1)
            except Exception:  # noqa: BLE001
                pass
        log.info('Đã xử lý {} khung hình. Thoát.'.format(frames))
        spin_thread.join(timeout=1.0)
        executor.shutdown(timeout_sec=1.0)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
