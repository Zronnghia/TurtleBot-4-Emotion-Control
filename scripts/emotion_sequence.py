#!/usr/bin/env python3
"""Phát một chuỗi biểu cảm giả lên /detected_emotion – thử emotion_behavior_node KHÔNG cần webcam.

  ros2 run tb4_lab04 emotion_sequence.py --ros-args -p preset:=all
  ros2 run tb4_lab04 emotion_sequence.py --ros-args -p sequence:="neutral:ready,happy:done,neutral:2"

Mỗi phần tử "nhãn:thời_lượng", nhãn được gửi liên tục 20 Hz (giống emotion_recognition_node):
  happy:2.5    gửi 2,5 s (giờ thực)
  happy:done   gửi tới khi robot CHẠY XONG quỹ đạo (đọc /emotion_behavior/state) – không phụ thuộc tốc độ
               Gazebo (máy yếu, real-time factor thấp)
  neutral:ready gửi tới khi robot sẵn sàng (đã undock + ra giữa sân, trạng thái IDLE)
Hết chuỗi -> NGỪNG gửi -> robot mất tín hiệu -> dừng (đúng thiết kế). Chỉ dùng để kiểm thử; video demo
phải dùng webcam thật.
"""

import json
import signal
import sys
import time

PRESETS = {
    # đủ 6 biểu cảm, mỗi quỹ đạo chạy hết rồi về neutral
    'all': ('neutral:ready,happy:done,neutral:2,sad:done,neutral:2,angry:done,neutral:2,'
            'surprise:done,neutral:2,fear:done,neutral:2'),
    # neutral dừng giữa chừng, biểu cảm mới ngắt quỹ đạo cũ, không thấy mặt -> dừng
    'interrupt': ('neutral:ready,surprise:started,surprise:1.5,neutral:3,surprise:started,surprise:1.5,'
                  'happy:done,neutral:2,sad:started,sad:1.5,no_face:3,neutral:2'),
    # giữ nguyên happy: mode once chỉ chạy 1 lần
    'hold': 'neutral:ready,happy:done,happy:6,neutral:2',
    # mất tín hiệu giữa quỹ đạo
    'lost': 'neutral:ready,surprise:started,surprise:1.5',
}
WAIT_KEYS = ('done', 'ready', 'started')


def parse_sequence(text):
    out = []
    for item in str(text).split(','):
        item = item.strip()
        if not item:
            continue
        name, _, dur = item.partition(':')
        dur = dur.strip().lower()
        if dur in WAIT_KEYS:
            out.append((name.strip(), dur))
        else:
            out.append((name.strip(), float(dur) if dur else 1.0))
    return out


def main(argv=None):
    import rclpy
    from rclpy.node import Node
    from rclpy.signals import SignalHandlerOptions
    from std_msgs.msg import String

    rclpy.init(args=argv, signal_handler_options=SignalHandlerOptions.NO)
    node = Node('emotion_sequence')
    preset = node.declare_parameter('preset', '').value
    seq_text = node.declare_parameter('sequence', '').value or PRESETS.get(preset, '')
    rate = float(node.declare_parameter('rate', 20.0).value)
    topic = node.declare_parameter('topic', '/detected_emotion').value
    state_topic = node.declare_parameter('state_topic', '/emotion_behavior/state').value
    wait_timeout = float(node.declare_parameter('wait_timeout', 900.0).value)
    if not seq_text:
        node.get_logger().error('Cần -p sequence:="nhan:giay,..." hoặc -p preset:={}'.format('|'.join(PRESETS)))
        return 2
    seq = parse_sequence(seq_text)
    pub = node.create_publisher(String, topic, 10)
    robot = {'state': None, 'active': None}

    def on_state(msg):
        try:
            d = json.loads(msg.data)
            robot['state'], robot['active'] = d.get('state'), d.get('active')
        except ValueError:
            pass

    node.create_subscription(String, state_topic, on_state, 10)
    stop = {'flag': False}
    signal.signal(signal.SIGINT, lambda *a: stop.__setitem__('flag', True))
    time.sleep(1.0)
    code = 0
    try:
        for name, dur in seq:
            node.get_logger().info('-> {} ({})'.format(name, dur if isinstance(dur, str) else '{:.1f} s'.format(dur)))
            t0 = time.monotonic()
            seen_exec = False
            while not stop['flag']:
                pub.publish(String(data=name))
                rclpy.spin_once(node, timeout_sec=0.0)
                time.sleep(1.0 / rate)
                el = time.monotonic() - t0
                st = robot['state']
                if isinstance(dur, float):
                    if el >= dur:
                        break
                    continue
                if el > wait_timeout:
                    node.get_logger().error('Quá {:.0f} s chờ "{}" – dừng chuỗi'.format(wait_timeout, dur))
                    stop['flag'] = True
                    code = 1
                    break
                if st == 'EXECUTING' and robot['active'] == name:
                    seen_exec = True
                if dur == 'ready' and st == 'IDLE':
                    break
                if dur == 'started' and seen_exec:
                    break
                if dur == 'done' and seen_exec and st != 'EXECUTING':
                    break
            if stop['flag']:
                break
        node.get_logger().info('Hết chuỗi – ngừng gửi (emotion_behavior_node sẽ báo mất tín hiệu)')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return code


if __name__ == '__main__':
    sys.exit(main())
