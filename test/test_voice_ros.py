#!/usr/bin/env python3
"""Test node voice_navigator.py với rclpy THẬT nhưng không cần Gazebo/Nav2 (tự bỏ qua nếu chưa source ROS).

Chạy trên ROS_DOMAIN_ID riêng -> không bao giờ gửi goal tới robot / mô phỏng đang chạy trên máy.

    source /opt/ros/humble/setup.bash && python3 -m pytest test/test_voice_ros.py -q
"""
import importlib.util
import os
import random
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))

try:
    import importlib
    for _m in ('rclpy', 'std_msgs.msg', 'nav2_msgs.action'):
        importlib.import_module(_m)
    HAVE_ROS = True
except ImportError:
    HAVE_ROS = False


def load(rel_path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@unittest.skipUnless(HAVE_ROS, 'chưa source ROS 2 (rclpy, nav2_msgs)')
class TestVoiceNavigatorNode(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ['ROS_DOMAIN_ID'] = str(random.randint(150, 200))      # cô lập khỏi robot thật
        import rclpy
        from rclpy.node import Node
        from rclpy.parameter import Parameter
        from std_msgs.msg import String
        rclpy.init()
        vn = load('scripts/voice_navigator.py', 'voice_navigator')
        cls.rclpy = rclpy
        cls.nav = vn.build_node_class()()
        cls.nav.set_parameters([Parameter('sim_time', Parameter.Type.BOOL, False),
                                Parameter('use_sim_time', Parameter.Type.BOOL, False),
                                Parameter('nav2_wait', Parameter.Type.DOUBLE, 2.0),
                                Parameter('results_dir', Parameter.Type.STRING,
                                          os.path.join(os.environ.get('TMPDIR', '/tmp'), 'tb4_voice_test'))])
        cls.listener = Node('tb4_voice_test_listener')
        cls.feedback = []
        cls.listener.create_subscription(String, 'voice/feedback', lambda m: cls.feedback.append(m.data), 10)
        cls.pub = cls.listener.create_publisher(String, 'voice/text', 10)

    @classmethod
    def tearDownClass(cls):
        cls.nav.destroy_node()
        cls.listener.destroy_node()
        cls.rclpy.shutdown()

    def spin(self, sec):
        end = time.monotonic() + sec
        while time.monotonic() < end:
            self.rclpy.spin_once(self.nav, timeout_sec=0.02)
            self.rclpy.spin_once(self.listener, timeout_sec=0.02)

    def send(self, text, wait=0.6):
        from std_msgs.msg import String
        end = time.monotonic() + 3.0
        while self.pub.get_subscription_count() == 0 and time.monotonic() < end:
            self.spin(0.05)
        del self.feedback[:]
        self.pub.publish(String(data=text))
        self.spin(wait)
        return list(self.feedback)

    def test_unknown_zone_does_not_crash(self):
        """Hồi quy: rclpy ném 'Logger severity cannot be changed between calls' khi say() log warn sau info."""
        fb = self.send('Đi đến khu vực Z')
        self.assertTrue(any('Không có khu vực' in f for f in fb), fb)
        fb = self.send('Có những khu vực nào?')
        self.assertTrue(any('Phòng học (A)' in f for f in fb), fb)
        fb = self.send('đi tới nhà bếp')
        self.assertTrue(any('nhà bếp' in f for f in fb), fb)
        self.assertIsNone(self.nav.mission)

    def test_where_without_tf(self):
        fb = self.send('tôi đang ở đâu')
        self.assertTrue(any('Chưa xác định' in f for f in fb), fb)

    def test_navigate_without_nav2_aborts_cleanly(self):
        self.nav.is_docked = False
        fb = self.send('Di chuyển từ khu vực A đến khu vực B', wait=1.0)
        joined = ' | '.join(fb)
        self.assertIn('Lộ trình', joined)
        self.assertIn('Phòng học (A)', joined)          # chưa biết vị trí -> đi qua A trước
        self.assertIn('đang chờ', joined)              # nói lệnh sớm -> chờ Nav2, không bỏ lệnh ngay
        self.assertIsNotNone(self.nav.mission)
        fb = self.send('', wait=3.0)                   # hết nav2_wait (2 s) -> mới huỷ, báo rõ lý do
        self.assertIn('Nav2 chưa sẵn sàng sau', ' | '.join(self.feedback + fb))
        self.assertIsNone(self.nav.mission)
        fb = self.send('dừng lại')
        self.assertTrue(any('đứng yên' in f for f in fb), fb)

    def test_command_during_undock_waits(self):
        """Lệnh mới trong lúc undock: không undock lần 2, không gửi chặng – chờ undock xong."""
        self.nav.undocking = True
        self.nav.is_docked = True
        try:
            fb = self.send('đi đến khu vực C', wait=1.0)
            joined = ' | '.join(fb)
            self.assertIn('Lộ trình', joined)
            self.assertNotIn('undock trước', joined)
            self.assertNotIn('Chặng', joined)
            self.assertIsNotNone(self.nav.mission)
            self.assertEqual(self.nav.mission['legs'], ['C'])
            fb = self.send('dừng lại')
            self.assertTrue(any('Đã dừng' in f and 'lùi nốt' in f for f in fb), fb)   # undock được làm nốt
            self.assertIsNone(self.nav.mission)
        finally:
            self.nav.undocking = False
            self.nav.is_docked = False


if __name__ == '__main__':
    unittest.main()
