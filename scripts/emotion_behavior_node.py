#!/usr/bin/env python3
"""Bài 8 – node điều khiển TurtleBot 4 theo BIỂU CẢM khuôn mặt (publish /cmd_vel).

  ros2 run tb4_lab04 emotion_behavior_node.py
  ros2 launch tb4_lab04 emotion.launch.py            # cùng emotion_recognition_node

Subscribe /detected_emotion (std_msgs/String – biểu cảm ỔN ĐỊNH, gửi mỗi khung) -> EmotionController
(emotion_logic.py) -> SegmentRunner (Bài 6: đo bằng /odom, tăng/giảm tốc mượt) -> /cmd_vel (Twist).

  happy    -> cung tròn sang trái (r 0,30 m, 90°)     sad      -> cung tròn sang phải
  neutral  -> DỪNG tại chỗ                            angry    -> lùi nhẹ 0,20 m
  surprise -> xoay 1 vòng tại chỗ                     fear     -> tiến nhẹ 0,20 m
  disgust  -> không làm gì (đề bài không yêu cầu)     no_face  -> dừng (stop_on_no_face)

Mỗi biểu cảm chạy MỘT quỹ đạo hữu hạn khi biểu cảm ổn định ĐỔI sang nó (mode:=once, mặc định). Giữ nguyên
biểu cảm không lặp lại; muốn chạy lại: về neutral rồi biểu cảm đó. mode:=repeat -> lặp khi còn giữ.
Biểu cảm mới trong lúc đang chạy -> chuyển ngay sang quỹ đạo mới (giảm tốc mượt, không giật).

An toàn: watchdog (mất /detected_emotion > 1 s -> dừng), LiDAR /scan (vật cản < 0,40 m theo hướng chạy
-> dừng), kẹt / quá thời gian -> dừng, Ctrl+C -> Twist 0. Khởi động ở dock: tự undock + chạy thẳng 1 m.
Kết quả: ~/tb4_results/emotion_<thời_gian>/events.csv, odom.csv (vẽ: plot_emotion_run.py).
"""

import csv
import json
import math
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import emotion_logic as el  # noqa: E402
import gesture_logic as gl  # noqa: E402


def main(argv=None):
    import rclpy
    from geometry_msgs.msg import Twist
    from nav_msgs.msg import Odometry
    from rclpy.clock import Clock, ClockType
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from rclpy.signals import SignalHandlerOptions
    from sensor_msgs.msg import LaserScan
    from std_msgs.msg import String

    try:
        from irobot_create_msgs.action import Undock
        from irobot_create_msgs.msg import DockStatus
    except ImportError:
        Undock = DockStatus = None

    class EmotionBehaviorNode(Node):
        def __init__(self):
            super().__init__('emotion_behavior_node')
            P = self._param
            self.prm = {
                'emotion_topic': P('emotion_topic', '/detected_emotion'),
                'cmd_vel_topic': P('cmd_vel_topic', '/cmd_vel'),
                'odom_topic': P('odom_topic', '/odom'),
                'scan_topic': P('scan_topic', '/scan'),
                'state_topic': P('state_topic', '/emotion_behavior/state'),
                'control_rate': float(P('control_rate', 20.0)),
                'mode': str(P('mode', 'once')),
                'signal_timeout': float(P('signal_timeout', 1.0)),
                'stop_on_no_face': el.as_bool(P('stop_on_no_face', True)),
                'repeat_delay': float(P('repeat_delay', 1.0)),
                'min_interval': float(P('min_interval', 0.5)),
                'odom_timeout': float(P('odom_timeout', 1.0)),
                'max_lin_acc': float(P('max_lin_acc', 0.5)),
                'max_ang_acc': float(P('max_ang_acc', 2.0)),
                'stall_timeout': float(P('stall_timeout', 4.0)),
                'use_scan_safety': el.as_bool(P('use_scan_safety', True)),
                'obstacle_stop_distance': float(P('obstacle_stop_distance', 0.40)),
                'obstacle_half_angle': float(P('obstacle_half_angle', 0.6)),
                'lidar_yaw': float(P('lidar_yaw', float('nan'))),
                'auto_undock': el.as_bool(P('auto_undock', True)),
                'dock_wait': float(P('dock_wait', 8.0)),
                'undock_timeout': float(P('undock_timeout', 90.0)),
                'setup_forward': float(P('setup_forward', 1.0)),
                'setup_speed': float(P('setup_speed', 0.2)),
                'stop_burst': int(P('stop_burst', 5)),
                'save_results': el.as_bool(P('save_results', True)),
            }
            self.eparams = {k: float(P(k, v)) for k, v in el.DEFAULT_EMOTION_PARAMS.items()}
            mode = self.prm['mode'] if self.prm['mode'] in ('once', 'repeat') else 'once'
            if mode != self.prm['mode']:
                self.get_logger().warn('mode "{}" không hợp lệ -> dùng once'.format(self.prm['mode']))
            self.ctl = el.EmotionController(mode, self.prm['signal_timeout'], self.prm['stop_on_no_face'],
                                            self.prm['repeat_delay'], self.prm['min_interval'])
            self.steady = Clock(clock_type=ClockType.STEADY_TIME)
            self.t0 = time.monotonic()
            self.pub_cmd = self.create_publisher(Twist, self.prm['cmd_vel_topic'], 10)
            self.pub_state = self.create_publisher(String, self.prm['state_topic'], 10)
            self.create_subscription(String, self.prm['emotion_topic'], self.on_emotion, 10)
            self.create_subscription(Odometry, self.prm['odom_topic'], self.on_odom, qos_profile_sensor_data)
            self.create_subscription(LaserScan, self.prm['scan_topic'], self.on_scan, qos_profile_sensor_data)
            self.pose = self.pose_t = self.odom_stamp = self.last_odom_stamp = None
            self.robot_t = 0.0
            self.last_tick_wall = None
            self.scan = self.scan_t = None
            self.lidar_yaw = None if math.isnan(self.prm['lidar_yaw']) else self.prm['lidar_yaw']
            self.tf_buffer = None
            self.runner = None
            self.runner_kind = None          # 'emotion' | 'setup'
            self.zero_left = 0
            self.last_key = None
            self.last_emotion = None
            self.warned = set()
            self.last_error_log = -1e9
            self.dock_status = None
            self.setup_phase = None
            self.setup_t0 = 0.0
            self.undock_client = self.undock_goal = self.undock_future = self.undock_result_future = None
            if DockStatus is not None:
                self.create_subscription(DockStatus, '/dock_status', self.on_dock, qos_profile_sensor_data)
            if self.prm['auto_undock'] and Undock is not None:
                from rclpy.action import ActionClient
                self.undock_client = ActionClient(self, Undock, '/undock')
                self.setup_phase = 'wait_dock'
                self.ctl.begin_setup('Kiem tra dock...')
            elif self.prm['auto_undock']:
                self.get_logger().warn('Không có irobot_create_msgs – bỏ qua bước tự undock')
            if self.prm['use_scan_safety']:
                self._init_tf()
            self._init_results()
            self.create_timer(1.0 / max(1.0, self.prm['control_rate']), self.control_tick, clock=self.steady)
            self.create_timer(0.2, self.publish_state, clock=self.steady)
            lines = ['=== emotion_behavior_node: điều khiển TurtleBot 4 bằng biểu cảm (mode={}) ==='.format(mode)]
            lines += el.describe_plans(self.eparams)
            lines.append('  mất /detected_emotion > {:.1f} s -> dừng; no_face -> {}'.format(
                self.prm['signal_timeout'], 'dừng' if self.prm['stop_on_no_face'] else 'chạy tiếp'))
            if self.events_f is not None:
                lines.append('  Kết quả: {}'.format(self.results_dir))
            self.get_logger().info('\n'.join(lines))

        # ------------------------------------------------------------ tiện ích
        def _param(self, name, default):
            from rcl_interfaces.msg import ParameterDescriptor
            self.declare_parameter(name, default, ParameterDescriptor(dynamic_typing=True))
            value = self.get_parameter(name).value
            return default if value is None else value

        def now(self):
            return time.monotonic()

        def warn_once(self, key, text):
            if key not in self.warned:
                self.warned.add(key)
                self.get_logger().warn(text)

        def _init_tf(self):
            try:
                from tf2_ros.buffer import Buffer
                from tf2_ros.transform_listener import TransformListener
                self.tf_buffer = Buffer()
                self.tf_listener = TransformListener(self.tf_buffer, self)
            except Exception as exc:  # noqa: BLE001
                self.get_logger().warn('Không dùng được tf2 ({}) – dùng lidar_yaw mặc định'.format(exc))

        def _init_results(self):
            self.events_f = self.odom_f = None
            if not self.prm['save_results']:
                return
            try:
                root = os.path.expanduser(os.environ.get('TB4_RESULTS_DIR', '~/tb4_results'))
                self.results_dir = os.path.join(root, 'emotion_' + time.strftime('%Y%m%d_%H%M%S'))
                os.makedirs(self.results_dir, exist_ok=True)
                self.events_f = open(os.path.join(self.results_dir, 'events.csv'), 'w', newline='',
                                     encoding='utf-8')
                self.events_w = csv.writer(self.events_f)
                self.events_w.writerow(['t', 'type', 'emotion', 'state', 'active', 'detail', 'x', 'y', 'yaw'])
                self.odom_f = open(os.path.join(self.results_dir, 'odom.csv'), 'w', newline='', encoding='utf-8')
                self.odom_w = csv.writer(self.odom_f)
                self.odom_w.writerow(['t', 'sim_t', 'x', 'y', 'yaw', 'state', 'active', 'lin_cmd', 'ang_cmd'])
                self.last_odom_log = 0.0
            except OSError as exc:
                self.get_logger().warn('Không ghi được kết quả: {}'.format(exc))
                self.events_f = self.odom_f = None

        def record(self, kind, detail='', emotion=''):
            if self.events_f is None:
                return
            d = self.ctl.describe()
            x, y, yaw = self.pose if self.pose is not None else ('', '', '')
            fmt = (lambda v: '{:.4f}'.format(v) if v != '' else '')
            self.events_w.writerow(['{:.3f}'.format(self.now() - self.t0), kind, emotion, d['state'],
                                    d['active'] or '', detail, fmt(x), fmt(y), fmt(yaw)])
            self.events_f.flush()

        # ------------------------------------------------------------ callback
        def on_emotion(self, msg):
            try:
                label = el.parse_emotion_message(msg.data)
                if label != self.last_emotion:
                    self.record('emotion', emotion=label)
                    self.last_emotion = label
                self.execute(self.ctl.on_message(label, self.now()), label)
            except Exception as exc:  # noqa: BLE001
                self._callback_error('xử lý biểu cảm', exc)

        def on_odom(self, msg):
            p = msg.pose.pose
            q = p.orientation
            yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
            self.pose = (p.position.x, p.position.y, yaw)
            self.pose_t = self.now()
            st = msg.header.stamp
            self.odom_stamp = st.sec + st.nanosec * 1e-9

        def on_scan(self, msg):
            self.scan = msg
            self.scan_t = self.now()

        def on_dock(self, msg):
            self.dock_status = bool(msg.is_docked)

        # ------------------------------------------------------------ hành động
        def execute(self, actions, emotion=''):
            for act in actions:
                kind = act[0]
                if kind == 'stop':
                    self.halt(act[1])
                elif kind == 'start':
                    self.start_emotion(act[1])
                elif kind == 'info':
                    self.get_logger().info(act[1])
                self.record(kind, act[1] if len(act) > 1 else '', emotion)

        def halt(self, reason):
            was = self.runner is not None and self.runner_kind == 'emotion'
            if self.runner_kind == 'emotion':
                self.runner = None
                self.runner_kind = None
            self.zero_left = max(self.zero_left, self.prm['stop_burst'])
            self._publish(0.0, 0.0)
            self.get_logger().warn('DỪNG robot – {}{}'.format(reason, '' if was else ' (robot đang đứng yên)'))

        def start_emotion(self, emotion):
            try:
                plan = el.build_emotion_plan(emotion, self.eparams)
            except ValueError as exc:
                self.get_logger().error('Tham số quỹ đạo {} sai: {}'.format(emotion, exc))
                self.execute(self.ctl.on_finished(False, str(exc), self.now()))
                return
            if not plan:
                self.execute(self.ctl.on_finished(True, '', self.now()))
                return
            if self.dock_status and any(s.lin > 0 for s in plan):
                # robot còn trong dock (undock lỗi / tắt auto_undock): tiến / cung tròn sẽ húc vào dock
                self.get_logger().warn('Robot đang ở DOCK – bỏ qua {} (cần undock trước: '
                                       'ros2 action send_goal /undock irobot_create_msgs/action/Undock "{{}}")'.format(
                                           emotion))
                self.execute(self.ctl.on_finished(False, 'robot dang o dock', self.now()))
                return
            prev_cmd = self.runner.cmd if (self.runner is not None and self.runner_kind == 'emotion') else (0.0, 0.0)
            self.runner = gl.SegmentRunner(plan, self.prm['max_lin_acc'], self.prm['max_ang_acc'],
                                           stall_timeout=self.prm['stall_timeout'])
            self.runner.cmd = prev_cmd     # đang chạy quỹ đạo khác -> chuyển tiếp mượt (giới hạn gia tốc)
            self.runner_kind = 'emotion'
            self.zero_left = 0
            self.get_logger().info('>>> {} -> {} ({}, ~{:.1f} s)'.format(
                emotion.upper(), el.ACTION_TEXT[emotion], plan[0].name, self.runner.total_nominal))

        def _publish(self, lin, ang):
            t = Twist()
            t.linear.x = float(lin)
            t.angular.z = float(ang)
            self.pub_cmd.publish(t)

        # ------------------------------------------------------------ LiDAR
        def _lidar_yaw(self):
            if self.lidar_yaw is not None:
                return self.lidar_yaw
            frame = self.scan.header.frame_id if self.scan is not None else ''
            if self.tf_buffer is not None and frame:
                try:
                    from rclpy.time import Time
                    tr = self.tf_buffer.lookup_transform('base_link', frame, Time())
                    q = tr.transform.rotation
                    self.lidar_yaw = math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))
                    return self.lidar_yaw
                except Exception:  # noqa: BLE001
                    pass
            return math.pi / 2.0 if 'rplidar' in frame else 0.0

        def obstacle(self, lin):
            if not self.prm['use_scan_safety'] or abs(lin) < 0.01:
                return False, None
            if self.scan is None or self.now() - self.scan_t > 1.0:
                self.warn_once('scan', 'Chưa có /scan mới – chạy KHÔNG có kiểm tra vật cản LiDAR')
                return False, None
            s = self.scan
            return gl.obstacle_in_path(list(s.ranges), s.angle_min, s.angle_increment, s.range_min, s.range_max,
                                       self._lidar_yaw(), 1 if lin > 0 else -1,
                                       self.prm['obstacle_stop_distance'], self.prm['obstacle_half_angle'])

        # ------------------------------------------------------------ vòng điều khiển
        def fresh_pose(self):
            if self.pose is not None and self.now() - self.pose_t <= self.prm['odom_timeout']:
                return self.pose
            return None

        def _advance_robot_clock(self, now):
            # "đồng hồ robot" theo stamp /odom (giờ mô phỏng) -> Gazebo chạy chậm không bị báo kẹt/quá giờ oan
            wall_dt = 0.0 if self.last_tick_wall is None else max(0.0, now - self.last_tick_wall)
            self.last_tick_wall = now
            if self.fresh_pose() is not None and self.odom_stamp is not None:
                if self.last_odom_stamp is not None:
                    d = self.odom_stamp - self.last_odom_stamp
                    self.robot_t += d if 0.0 <= d < 5.0 else wall_dt
                self.last_odom_stamp = self.odom_stamp
            else:
                self.robot_t += wall_dt
                self.last_odom_stamp = None
            return self.robot_t

        def control_tick(self):
            try:
                self._control_tick()
            except Exception as exc:  # noqa: BLE001
                self._callback_error('vòng điều khiển', exc)

        def _callback_error(self, where, exc):
            now = self.now()
            if now - self.last_error_log > 5.0:
                self.last_error_log = now
                import traceback
                self.get_logger().error('Lỗi ở {}: {}: {}\n{}'.format(where, type(exc).__name__, exc,
                                                                      traceback.format_exc()))
            try:
                self.runner = None
                self.runner_kind = None
                self._publish(0.0, 0.0)
                self.zero_left = self.prm['stop_burst']
                if self.ctl.state == el.EXECUTING:
                    self.ctl.on_finished(False, 'loi phan mem: {}'.format(exc), self.now())
            except Exception:  # noqa: BLE001
                pass

        def _control_tick(self):
            now = self.now()
            rt = self._advance_robot_clock(now)
            self.execute(self.ctl.tick(now))
            self._setup_tick(rt)
            if self.runner is not None:
                pose = self.fresh_pose()
                if pose is None:
                    self.warn_once('odom', 'Không có /odom mới – đo chuyển động theo thời gian (kém chính xác)')
                lin, ang = self.runner.update(rt, pose)
                blocked, dist = self.obstacle(lin)
                kind = self.runner_kind
                if blocked or self.runner.error:
                    reason = self.runner.error or 'VAT CAN cach {:.2f} m phia {}'.format(
                        dist, 'truoc' if lin > 0 else 'sau')
                    self.runner = None
                    self.runner_kind = None
                    self.zero_left = self.prm['stop_burst']
                    self._publish(0.0, 0.0)
                    if kind == 'emotion':
                        self.execute(self.ctl.on_finished(False, reason, now))
                    else:
                        self._finish_setup('Dung ra giua san: ' + reason, ok=False)
                elif self.runner.done:
                    self.runner = None
                    self.runner_kind = None
                    self.zero_left = self.prm['stop_burst']
                    self._publish(0.0, 0.0)
                    if kind == 'emotion':
                        self.execute(self.ctl.on_finished(True, '', now))
                    else:
                        self._finish_setup('Da ra giua san - san sang nhan bieu cam')
                else:
                    self._publish(lin, ang)
            elif self.zero_left > 0:
                self.zero_left -= 1
                self._publish(0.0, 0.0)
            self._log_odom(now)

        # ------------------------------------------------------------ undock + ra giữa sân
        def _finish_setup(self, text, ok=True):
            self.setup_phase = None
            gl.log_at(self.get_logger(), 'info' if ok else 'warn', text)
            self.record('setup', text)
            self.ctl.end_setup(ok, text)

        def _setup_tick(self, now):
            ph = self.setup_phase
            if ph is None or ph == 'forward':
                return
            if ph == 'wait_dock':
                if self.dock_status is None:
                    if now - self.setup_t0 > self.prm['dock_wait']:
                        self._finish_setup('Khong nhan /dock_status - bo qua undock', ok=False)
                    return
                if not self.dock_status:
                    self._finish_setup('Robot khong o dock - bo qua undock, san sang')
                    return
                if not self.undock_client.server_is_ready():
                    if now - self.setup_t0 > self.prm['dock_wait'] + 10.0:
                        self._finish_setup('Khong thay action /undock - bo qua', ok=False)
                    return
                self.get_logger().info('Robot đang ở dock -> gửi /undock (lùi ra, quay 180°)')
                self.ctl.message = 'Dang undock...'
                self.undock_future = self.undock_client.send_goal_async(Undock.Goal())
                self.setup_phase = 'undocking'
                self.setup_t0 = now
                return
            if ph == 'undocking':
                if now - self.setup_t0 > self.prm['undock_timeout']:
                    self._cancel_undock()
                    self._finish_setup('Undock qua {:.0f} s - bo qua'.format(self.prm['undock_timeout']), ok=False)
                    return
                if self.undock_goal is None:
                    if self.undock_future is not None and self.undock_future.done():
                        gh = self.undock_future.result()
                        if gh is None or not gh.accepted:
                            self._finish_setup('Undock bi tu choi', ok=False)
                            return
                        self.undock_goal = gh
                        self.undock_result_future = gh.get_result_async()
                    return
                if self.undock_result_future.done():
                    status = getattr(self.undock_result_future.result(), 'status', 0)
                    self.undock_goal = None
                    if status != 4:
                        self._finish_setup('Undock khong thanh cong (status {})'.format(status), ok=False)
                        return
                    d = self.prm['setup_forward']
                    if d <= 0.01:
                        self._finish_setup('Undock xong - san sang nhan bieu cam')
                        return
                    self.get_logger().info('Undock xong -> chạy thẳng {:.2f} m ra giữa sân'.format(d))
                    self.ctl.message = 'Ra giua san {:.1f} m...'.format(d)
                    self.runner = gl.SegmentRunner(
                        [gl.Segment('ra giua san', abs(self.prm['setup_speed']), 0.0, d, 'dist')],
                        self.prm['max_lin_acc'], self.prm['max_ang_acc'], stall_timeout=self.prm['stall_timeout'])
                    self.runner_kind = 'setup'
                    self.setup_phase = 'forward'

        def _cancel_undock(self):
            if self.undock_goal is not None:
                try:
                    self.undock_goal.cancel_goal_async()
                except Exception:  # noqa: BLE001
                    pass
            self.undock_goal = None
            self.undock_future = None

        # ------------------------------------------------------------ log / trạng thái
        def _log_odom(self, now):
            if self.odom_f is None or self.pose is None or now - self.last_odom_log < 0.1:
                return
            self.last_odom_log = now
            d = self.ctl.describe()
            lin, ang = self.runner.cmd if self.runner is not None else (0.0, 0.0)
            active = 'setup' if (self.runner_kind == 'setup' or self.setup_phase) else (d['active'] or '')
            self.odom_w.writerow(['{:.3f}'.format(now - self.t0), '{:.3f}'.format(self.robot_t),
                                  '{:.4f}'.format(self.pose[0]),
                                  '{:.4f}'.format(self.pose[1]), '{:.4f}'.format(self.pose[2]), d['state'],
                                  active, '{:.3f}'.format(lin), '{:.3f}'.format(ang)])

        def publish_state(self):
            d = self.ctl.describe()
            d['progress'] = (round(self.runner.overall_progress(), 2)
                             if self.runner is not None and self.runner_kind == 'emotion' else None)
            d['docked'] = self.dock_status
            self.pub_state.publish(String(data=json.dumps(d, ensure_ascii=True)))
            key = (d['state'], d['active'], d['message'])
            if key != self.last_key:
                self.last_key = key
                self.get_logger().info('[trạng thái] {:<11} biểu cảm={:<8} chạy={:<8} {}'.format(
                    d['state'], d['emotion'], d['active'] or '-', d['message']))

        def shutdown(self):
            for _ in range(3):
                self._publish(0.0, 0.0)
                time.sleep(0.02)
            self._cancel_undock()
            for f in (self.events_f, self.odom_f):
                if f is not None:
                    try:
                        f.close()
                    except OSError:
                        pass

    rclpy.init(args=argv, signal_handler_options=SignalHandlerOptions.NO)
    stop = {'flag': False, 'count': 0}

    def on_signal(signum, frame):
        stop['count'] += 1
        stop['flag'] = True
        if stop['count'] >= 3:
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    node = EmotionBehaviorNode()
    code = 0
    try:
        while rclpy.ok() and not stop['flag']:
            rclpy.spin_once(node, timeout_sec=0.05)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # noqa: BLE001
        node.get_logger().error('Lỗi: {}: {}'.format(type(exc).__name__, exc))
        code = 1
    finally:
        node.get_logger().info('Thoát – gửi Twist 0 để robot dừng')
        try:
            node.shutdown()
        finally:
            node.destroy_node()
            if rclpy.ok():
                rclpy.shutdown()
    return code


if __name__ == '__main__':
    sys.exit(main())
