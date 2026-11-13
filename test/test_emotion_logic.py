#!/usr/bin/env python3
"""Unit test Bài 8 – nhận diện biểu cảm -> quỹ đạo TurtleBot 4 (không cần ROS, webcam, DeepFace/FER).

    python3 test/test_emotion_logic.py          # hoặc: python3 -m pytest test/ -q
Test dùng DeepFace / FER thật tự BỎ QUA nếu máy chưa cài (bash scripts/install_emotion_deps.sh).
"""
import importlib.util
import math
import os
import re
import subprocess
import sys
import types
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))


def load(rel_path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


el = load('scripts/emotion_logic.py', 'emotion_logic')
eb = load('scripts/emotion_backends.py', 'emotion_backends')
es = load('scripts/emotion_sequence.py', 'emotion_sequence')
gl = load('scripts/gesture_logic.py', 'gesture_logic')
ern = load('scripts/emotion_recognition_node.py', 'emotion_recognition_node')


def has(mod):
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def simulate(plan, rate=20.0, lag=0.1, max_t=120.0, start=(0.0, 0.0, 0.0), preempt=None):
    """Chạy SegmentRunner trên mô hình robot vi sai lý tưởng + trễ bậc nhất (lag s). Trả (pose cuối, runner)."""
    runner = gl.SegmentRunner(plan, period=1.0 / rate)
    x, y, th = start
    v = w = 0.0
    t = 0.0
    dt = 1.0 / rate
    while not runner.done and runner.error is None and t < max_t:
        lin, ang = runner.update(t, (x, y, th))
        k = dt / (lag + dt)
        v += k * (lin - v)
        w += k * (ang - w)
        x += v * math.cos(th) * dt
        y += v * math.sin(th) * dt
        th += w * dt
        t += dt
    for _ in range(int(1.0 / dt)):           # robot trôi nốt sau lệnh 0
        k = dt / (lag + dt)
        v -= k * v
        w -= k * w
        x += v * math.cos(th) * dt
        y += v * math.sin(th) * dt
        th += w * dt
    return (x, y, th), runner, t


def feed(stab, label, t0, dur, fps=30.0):
    changes = []
    n = int(round(dur * fps))
    t = t0
    for i in range(n):
        t = t0 + i / fps
        st, ch = stab.update(t, label)
        if ch:
            changes.append((round(t, 3), st))
    return changes, t + 1.0 / fps


# ----------------------------------------------------------------------------------------------------
class TestLabels(unittest.TestCase):
    def test_canonical(self):
        self.assertEqual(el.canonical_emotion(' Happy '), 'happy')
        self.assertEqual(el.canonical_emotion('HAPPINESS'), 'happy')
        self.assertEqual(el.canonical_emotion('surprised'), 'surprise')
        self.assertEqual(el.canonical_emotion(None), el.NO_FACE)
        self.assertEqual(el.canonical_emotion(''), el.NO_FACE)
        self.assertEqual(el.canonical_emotion('banana'), el.UNKNOWN)

    def test_parse_message(self):
        self.assertEqual(el.parse_emotion_message('sad'), 'sad')
        self.assertEqual(el.parse_emotion_message('{"stable": "fear", "raw": "x"}'), 'fear')
        self.assertEqual(el.parse_emotion_message('{bad json'), el.UNKNOWN)
        self.assertEqual(el.parse_emotion_message(''), el.NO_FACE)

    def test_normalize_percent_and_fraction(self):
        p = el.normalize_probs({'happy': 90.0, 'neutral': 10.0})       # DeepFace: %
        self.assertAlmostEqual(p['happy'], 0.9)
        q = el.normalize_probs({'happy': 0.9, 'neutral': 0.1})         # FER: 0..1
        self.assertAlmostEqual(q['happy'], 0.9)
        self.assertEqual(set(p), set(el.EMOTIONS))
        self.assertAlmostEqual(sum(p.values()), 1.0)

    def test_normalize_garbage(self):
        p = el.normalize_probs({'happy': float('nan'), 'sad': 'x', 'zzz': 5, 'fear': -1})
        self.assertEqual(sum(p.values()), 0.0)
        self.assertEqual(sum(el.normalize_probs(None).values()), 0.0)

    def test_frame_label(self):
        probs = el.normalize_probs({'happy': 0.8, 'neutral': 0.2})
        self.assertEqual(el.frame_label(probs, True)[0], 'happy')
        self.assertEqual(el.frame_label(probs, False)[0], el.NO_FACE)
        close = el.normalize_probs({'happy': 0.45, 'neutral': 0.40, 'sad': 0.15})
        self.assertEqual(el.frame_label(close, True)[0], el.UNKNOWN)          # sát lớp thứ 2
        low = el.normalize_probs({e: 1.0 for e in el.EMOTIONS})
        self.assertEqual(el.frame_label(low, True)[0], el.UNKNOWN)            # 1/7 < 0,4
        self.assertEqual(el.frame_label(None, True)[0], el.UNKNOWN)

    def test_smoother(self):
        s = el.ProbSmoother(0.5)
        a = el.normalize_probs({'happy': 1.0})
        b = el.normalize_probs({'sad': 1.0})
        s.update(a)
        v = s.update(b)
        self.assertAlmostEqual(v['happy'], 0.5)
        self.assertAlmostEqual(v['sad'], 0.5)
        self.assertIsNone(s.update(None))


class TestStabilizer(unittest.TestCase):
    def make(self):
        return el.EmotionStabilizer(hold_time=0.6, hold_overrides={'neutral': 0.4, el.NO_FACE: 0.5},
                                    vote_ratio=0.6, min_frames=3)

    def test_switch_after_hold(self):
        s = self.make()
        ch, t = feed(s, 'happy', 0.0, 1.0)
        self.assertEqual([c[1] for c in ch], ['happy'])
        self.assertGreaterEqual(ch[0][0], 0.45)        # >= 80 % hold
        self.assertLess(ch[0][0], 0.7)

    def test_flicker_ignored(self):
        s = self.make()
        _, t = feed(s, 'happy', 0.0, 1.0)
        for i in range(30):                             # 1 khung sad mỗi 5 khung
            lab = 'sad' if i % 5 == 0 else 'happy'
            st, ch = s.update(t + i / 30.0, lab)
            self.assertFalse(ch)
        self.assertEqual(s.stable, 'happy')

    def test_unknown_keeps_label(self):
        s = self.make()
        _, t = feed(s, 'happy', 0.0, 1.0)
        ch, t = feed(s, el.UNKNOWN, t, 3.0)
        self.assertEqual(ch, [])
        self.assertEqual(s.stable, 'happy')

    def test_neutral_faster_than_emotion(self):
        s = self.make()
        _, t = feed(s, 'happy', 0.0, 1.0)
        ch, _ = feed(s, 'neutral', t, 1.0)
        self.assertEqual(ch[0][1], 'neutral')
        self.assertLess(ch[0][0] - t, 0.45)

    def test_no_face(self):
        s = self.make()
        _, t = feed(s, 'sad', 0.0, 1.0)
        ch, _ = feed(s, el.NO_FACE, t, 1.0)
        self.assertEqual(ch[0][1], el.NO_FACE)

    def test_change_between_emotions(self):
        s = self.make()
        _, t = feed(s, 'happy', 0.0, 1.0)
        ch, _ = feed(s, 'surprise', t, 1.5)
        self.assertEqual([c[1] for c in ch], ['surprise'])


class TestPlans(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(el.build_emotion_plan('neutral'), [])
        self.assertIsNone(el.build_emotion_plan('disgust'))
        self.assertIsNone(el.build_emotion_plan(el.NO_FACE))
        for e in el.ACTION_EMOTIONS:
            self.assertTrue(el.build_emotion_plan(e))

    def test_happy_curves_left_sad_right(self):
        _, (x, y, th) = gl.plan_extent(el.build_emotion_plan('happy'))
        self.assertGreater(x, 0.2)
        self.assertGreater(y, 0.2)                     # lệch TRÁI (y+)
        self.assertAlmostEqual(math.degrees(th), 90.0, delta=1.0)
        _, (x2, y2, th2) = gl.plan_extent(el.build_emotion_plan('sad'))
        self.assertGreater(x2, 0.2)
        self.assertLess(y2, -0.2)                      # lệch PHẢI
        self.assertAlmostEqual(math.degrees(th2), -90.0, delta=1.0)
        self.assertAlmostEqual(x, x2, places=3)        # đối xứng
        self.assertAlmostEqual(y, -y2, places=3)

    def test_arc_geometry(self):
        p = {'arc_radius': 0.3, 'arc_angle': 90.0}
        _, (x, y, _) = gl.plan_extent(el.build_emotion_plan('happy', p))
        self.assertAlmostEqual(x, 0.3, delta=0.01)     # cung 1/4 tròn r = 0,3 -> (r, r)
        self.assertAlmostEqual(y, 0.3, delta=0.01)

    def test_angry_back_fear_forward(self):
        _, (x, y, th) = gl.plan_extent(el.build_emotion_plan('angry'))
        self.assertAlmostEqual(x, -0.20, delta=0.01)
        self.assertAlmostEqual(y, 0.0, delta=1e-6)
        _, (x, y, th) = gl.plan_extent(el.build_emotion_plan('fear'))
        self.assertAlmostEqual(x, 0.20, delta=0.01)
        self.assertLess(abs(th), 1e-6)

    def test_surprise_full_turn_in_place(self):
        plan = el.build_emotion_plan('surprise')
        self.assertAlmostEqual(sum(s.target for s in plan), 2 * math.pi)
        rmax, (x, y, th) = gl.plan_extent(plan)
        self.assertLess(rmax, 1e-6)
        self.assertLess(abs(math.atan2(math.sin(th), math.cos(th))), 0.05)

    def test_small_motions(self):
        """'nhẹ' = không ra xa điểm xuất phát quá 0,5 m, mỗi quỹ đạo < 10 s."""
        for e in el.ACTION_EMOTIONS:
            plan = el.build_emotion_plan(e)
            rmax, _ = gl.plan_extent(plan)
            self.assertLess(rmax, 0.5, e)
            self.assertLess(sum(s.nominal_duration() for s in plan), 10.0, e)

    def test_bad_params(self):
        with self.assertRaises(ValueError):
            el.build_emotion_plan('happy', {'arc_radius': 0.0})
        with self.assertRaises(ValueError):
            el.build_emotion_plan('fear', {'forward_speed': 0.0})
        lines = el.describe_plans({'spin_speed': 0.0})
        self.assertTrue(any('THAM SO SAI' in ln for ln in lines))

    def test_runner_accuracy(self):
        """SegmentRunner + robot có trễ: kết thúc đúng quỹ đạo (sai số nhỏ, không vọt đích)."""
        for e, check in (
                ('happy', lambda x, y, th: abs(math.degrees(th) - 90) < 4 and y > 0.25),
                ('sad', lambda x, y, th: abs(math.degrees(th) + 90) < 4 and y < -0.25),
                ('angry', lambda x, y, th: abs(x + 0.20) < 0.015 and abs(th) < 0.01),
                ('fear', lambda x, y, th: abs(x - 0.20) < 0.015 and abs(th) < 0.01),
                ('surprise', lambda x, y, th: abs(math.degrees(th) - 360) < 6 and math.hypot(x, y) < 1e-6)):
            (x, y, th), runner, t = simulate(el.build_emotion_plan(e))
            self.assertTrue(runner.done, e)
            self.assertIsNone(runner.error, e)
            self.assertTrue(check(x, y, th), '{}: ({:.3f}, {:.3f}, {:.1f} deg)'.format(e, x, y, math.degrees(th)))

    def test_runner_without_odom(self):
        runner = gl.SegmentRunner(el.build_emotion_plan('fear'))
        t = 0.0
        while not runner.done and t < 10:
            runner.update(t, None)
            t += 0.05
        self.assertTrue(runner.done)


class TestController(unittest.TestCase):
    def ctl(self, **kw):
        c = el.EmotionController(**kw)
        c.on_message('neutral', 0.0)
        return c

    @staticmethod
    def kinds(acts):
        return [a[0] for a in acts]

    def test_waiting_until_first_message(self):
        c = el.EmotionController()
        self.assertEqual(c.state, el.WAITING)
        self.assertEqual(c.tick(100.0), [])
        acts = c.on_message('neutral', 1.0)
        self.assertEqual(self.kinds(acts), ['info'])
        self.assertEqual(c.state, el.IDLE)

    def test_start_once(self):
        c = self.ctl()
        acts = c.on_message('happy', 1.0)
        self.assertEqual(acts, [('start', 'happy', None)])
        self.assertEqual(c.state, el.EXECUTING)
        self.assertEqual(c.on_message('happy', 1.1), [])
        c.on_finished(True, '', 5.0)
        self.assertEqual(c.state, el.IDLE)
        self.assertEqual(c.on_message('happy', 8.0), [])        # vẫn giữ happy -> KHÔNG lặp (mode once)
        self.assertEqual(c.count, {'happy': 1})

    def test_retrigger_after_neutral(self):
        c = self.ctl()
        c.on_message('happy', 1.0)
        c.on_finished(True, '', 5.0)
        c.on_message('neutral', 6.0)
        self.assertEqual(c.on_message('happy', 7.0), [('start', 'happy', None)])

    def test_neutral_stops(self):
        c = self.ctl()
        c.on_message('surprise', 1.0)
        acts = c.on_message('neutral', 2.0)
        self.assertEqual(self.kinds(acts), ['stop'])
        self.assertEqual(c.state, el.IDLE)
        self.assertIsNone(c.active)
        self.assertEqual(c.on_message('neutral', 2.1), [])      # đứng yên rồi: không gửi lại stop

    def test_preempt(self):
        c = self.ctl()
        c.on_message('surprise', 1.0)
        acts = c.on_message('happy', 2.0)
        self.assertEqual(acts, [('start', 'happy', 'surprise')])
        self.assertEqual(c.active, 'happy')

    def test_min_interval(self):
        c = self.ctl(min_interval=0.5)
        c.on_message('happy', 1.0)
        self.assertEqual(c.on_message('sad', 1.2), [])
        self.assertEqual(c.on_message('sad', 1.6), [('start', 'sad', 'happy')])

    def test_no_face(self):
        c = self.ctl(stop_on_no_face=True)
        c.on_message('fear', 1.0)
        self.assertEqual(self.kinds(c.on_message(el.NO_FACE, 2.0)), ['stop'])
        self.assertEqual(c.on_message('fear', 3.0), [('start', 'fear', None)])   # người quay lại -> chạy lại
        c2 = self.ctl(stop_on_no_face=False)
        c2.on_message('fear', 1.0)
        self.assertEqual(c2.on_message(el.NO_FACE, 2.0), [])
        self.assertEqual(c2.state, el.EXECUTING)

    def test_unknown_and_disgust_ignored(self):
        c = self.ctl()
        c.on_message('happy', 1.0)
        self.assertEqual(c.on_message(el.UNKNOWN, 2.0), [])
        self.assertEqual(c.on_message('disgust', 3.0), [])
        self.assertEqual(c.active, 'happy')
        self.assertEqual(c.on_message('happy', 4.0), [])         # unknown xen giữa không làm chạy lại

    def test_watchdog(self):
        c = self.ctl(signal_timeout=1.0)
        c.on_message('surprise', 1.0)
        self.assertEqual(c.tick(1.5), [])
        acts = c.tick(2.2)
        self.assertEqual(self.kinds(acts), ['stop'])
        self.assertEqual(c.state, el.SIGNAL_LOST)
        self.assertEqual(c.tick(3.0), [])
        acts = c.on_message('surprise', 4.0)                     # tín hiệu trở lại -> chạy lại
        self.assertEqual(self.kinds(acts), ['info', 'start'])

    def test_watchdog_idle_no_stop(self):
        c = self.ctl()
        self.assertEqual(c.tick(5.0), [])                        # đứng yên: chỉ đổi trạng thái
        self.assertEqual(c.state, el.SIGNAL_LOST)

    def test_repeat_mode(self):
        c = self.ctl(mode='repeat', repeat_delay=1.0)
        c.on_message('fear', 1.0)
        c.on_finished(True, '', 3.0)
        self.assertEqual(c.on_message('fear', 3.5), [])
        self.assertEqual(c.on_message('fear', 4.1), [('start', 'fear', None)])

    def test_failure_returns_stop(self):
        c = self.ctl()
        c.on_message('angry', 1.0)
        acts = c.on_finished(False, 'VAT CAN', 2.0)
        self.assertEqual(self.kinds(acts), ['stop'])
        self.assertEqual(c.state, el.IDLE)
        self.assertEqual(c.on_message('angry', 3.0), [])         # không lùi tiếp vào vật cản

    def test_setup_ignores_then_runs(self):
        c = el.EmotionController()
        c.begin_setup()
        self.assertEqual(c.on_message('happy', 1.0), [])
        self.assertEqual(c.tick(50.0), [])                       # không watchdog trong lúc chuẩn bị
        c.end_setup(True, 'xong')
        self.assertEqual(c.state, el.IDLE)
        self.assertEqual(c.on_message('happy', 51.0), [('start', 'happy', None)])

    def test_bad_mode(self):
        with self.assertRaises(ValueError):
            el.EmotionController(mode='forever')


class TestFaceTracker(unittest.TestCase):
    def test_geometry(self):
        self.assertAlmostEqual(eb.iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)
        self.assertEqual(eb.iou((0, 0, 10, 10), (20, 20, 5, 5)), 0.0)
        self.assertEqual(eb.expand_box((10, 10, 100, 100), 0.1, 105, 200), (0, 0, 105, 120))

    def test_pick_highest_score_not_largest(self):
        tr = eb.FaceTracker()
        box, real = tr.update(0.0, [(300, 120, 130, 130, 1.2), (180, 70, 90, 90, 5.7)])
        self.assertTrue(real)
        self.assertEqual(box[:2], (180.0, 70.0))

    def test_follow_same_face_and_hold(self):
        tr = eb.FaceTracker(alpha=0.5, hold_time=0.3)
        tr.update(0.0, [(100, 100, 80, 80)])
        box, _ = tr.update(0.1, [(110, 100, 80, 80), (400, 50, 150, 150, 9.0)])   # người khác lớn hơn
        self.assertAlmostEqual(box[0], 105.0)                   # vẫn bám mặt cũ, EMA
        box, real = tr.update(0.3, [])
        self.assertIsNotNone(box)
        self.assertFalse(real)
        box, real = tr.update(0.7, [])
        self.assertIsNone(box)

    def test_compat_shims(self):
        fake = types.ModuleType('fake_cv2')
        eb.install_compat_shims(fake)
        self.assertTrue(fake.data.haarcascades.endswith('/'))
        import pkg_resources  # noqa: F401  (có sẵn hoặc bản vá)


class TestDisplay(unittest.TestCase):
    def test_display_available(self):
        self.assertFalse(ern.display_available({}))
        self.assertTrue(ern.display_available({'WAYLAND_DISPLAY': 'wayland-0'}))
        self.assertFalse(ern.display_available({'DISPLAY': ':987654'}))          # không có socket X
        self.assertTrue(ern.display_available({'DISPLAY': 'localhost:10.0'}))    # ssh -X

    def test_draw_view(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest('cần OpenCV')
        img = np.zeros((480, 640, 3), np.uint8)
        probs = el.normalize_probs({'happy': 0.7, 'sad': 0.3})
        robot = {'state': 'EXECUTING', 'active': 'happy', 'progress': 0.5, 'message': 'Đang chạy – thử'}
        out = ern.draw_view(cv2, img, (100, 100, 120, 120), True, 'happy', 0.7, probs, 'happy', 0.9, 25.0,
                            'deepface', robot)
        self.assertEqual(out.shape, (480, 640 + ern.PANEL_W, 3))
        out = ern.draw_view(cv2, img, None, False, el.NO_FACE, 0.0, None, '-', 0.0, 0.0, 'fer', None,
                            source_ok=False)
        self.assertEqual(out.shape[1], 640 + ern.PANEL_W)


class TestLogging(unittest.TestCase):
    """Hồi quy: rclpy cấm đổi mức log ở CÙNG một dòng gọi (ValueError làm chết node / luồng camera)."""

    def test_log_at_dispatch(self):
        got = []

        class Fake:
            def __getattr__(self, name):
                return lambda msg: got.append((name, msg))
        for lv in ('warn', 'info', 'error', 'debug', 'fatal', 'xyz'):
            el.log_at(Fake(), lv, lv)
        self.assertEqual([g[0] for g in got], ['warning', 'info', 'error', 'debug', 'fatal', 'info'])

    @unittest.skipUnless(has('rclpy'), 'cần ROS 2 (rclpy)')
    def test_log_at_with_rclpy(self):
        import rclpy
        from rclpy.logging import get_logger
        lg = get_logger('test_emotion_log_at')
        for lv in ('warn', 'info', 'warn', 'error', 'info'):
            el.log_at(lg, lv, 'thử mức ' + lv)          # không được ném ValueError
        self.assertTrue(hasattr(rclpy, 'init'))

    def test_no_dynamic_severity_in_scripts(self):
        pat2 = re.compile(r"=\s*(self\.)?(log|logger|self\.get_logger\(\))\.(info|warn|warning|error) if ")
        pat3 = re.compile(r"\((self\.)?(log|self\.get_logger\(\))\.(info|warn|warning) if ")
        scripts = os.path.join(ROOT, 'scripts')
        for f in sorted(os.listdir(scripts)):
            if not f.endswith('.py'):
                continue
            for i, line in enumerate(open(os.path.join(scripts, f), encoding='utf-8'), 1):
                code = re.sub(r'`[^`]*`', '', line.split('#', 1)[0])     # bỏ ví dụ trong docstring
                self.assertIsNone(pat2.search(code), '{}:{}: {}'.format(f, i, line.strip()))
                self.assertIsNone(pat3.search(code), '{}:{}: {}'.format(f, i, line.strip()))
                self.assertNotRegex(code, r"getattr\((self\.)?(log|logger)\s*,", '{}:{}'.format(f, i))


class TestSequence(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(es.parse_sequence('neutral:ready, happy:done,sad:2.5,fear'),
                         [('neutral', 'ready'), ('happy', 'done'), ('sad', 2.5), ('fear', 1.0)])
        for name, text in es.PRESETS.items():
            for lab, _ in es.parse_sequence(text):
                self.assertIn(el.canonical_emotion(lab), el.ALL_LABELS, name)
                self.assertNotEqual(el.canonical_emotion(lab), el.UNKNOWN, name)


class TestConfig(unittest.TestCase):
    @staticmethod
    def declared(path):
        src = open(os.path.join(ROOT, path), encoding='utf-8').read()
        return set(re.findall(r"P\('(\w+)'", src))

    def test_yaml_keys_are_declared(self):
        cfg = yaml.safe_load(open(os.path.join(ROOT, 'config', 'emotion.yaml'), encoding='utf-8'))
        rec = self.declared('scripts/emotion_recognition_node.py')
        beh = self.declared('scripts/emotion_behavior_node.py') | set(el.DEFAULT_EMOTION_PARAMS)
        r = set(cfg['emotion_recognition_node']['ros__parameters'])
        b = set(cfg['emotion_behavior_node']['ros__parameters'])
        self.assertEqual(r - rec, set(), 'khoá YAML sai tên (recognition)')
        self.assertEqual(b - beh, set(), 'khoá YAML sai tên (behavior)')
        self.assertEqual(set(el.DEFAULT_EMOTION_PARAMS) - b, set())
        p = {k: cfg['emotion_behavior_node']['ros__parameters'][k] for k in el.DEFAULT_EMOTION_PARAMS}
        for e in el.ACTION_EMOTIONS:
            self.assertTrue(el.build_emotion_plan(e, p))
        self.assertIn(cfg['emotion_recognition_node']['ros__parameters']['backend'], eb.BACKENDS)

    def test_launch_overrides_exist(self):
        src = open(os.path.join(ROOT, 'launch', 'emotion.launch.py'), encoding='utf-8').read()
        rec = self.declared('scripts/emotion_recognition_node.py')
        beh = self.declared('scripts/emotion_behavior_node.py')
        for who, name in re.findall(r"\('(rec|beh)', '(\w+)'", src):
            self.assertIn(name, rec if who == 'rec' else beh, name)
            self.assertIn("DeclareLaunchArgument('{}'".format(
                re.search(r"'(\w+)': \('{}', '{}'".format(who, name), src).group(1)), src)

    def test_cascade_bundled(self):
        self.assertTrue(os.path.isfile(os.path.join(ROOT, 'models', eb.CASCADE_FILE)))

    def test_install_script_syntax(self):
        r = subprocess.run(['bash', '-n', os.path.join(ROOT, 'scripts', 'install_emotion_deps.sh')],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


@unittest.skipUnless(has('cv2') and has('numpy'), 'cần OpenCV')
class TestDetector(unittest.TestCase):
    def test_blank_image_no_face(self):
        import cv2
        import numpy as np
        det = eb.FaceDetector(cv2)
        self.assertEqual(det.detect(np.full((480, 640, 3), 127, np.uint8)), [])
        self.assertEqual(det.detect(np.zeros((480, 640), np.uint8)), [])


class TestBackends(unittest.TestCase):
    def check(self, name):
        import cv2
        import numpy as np
        b = eb.make_backend(name, log=lambda m: None, cv2=cv2)
        p = b.predict(np.full((240, 240, 3), 128, np.uint8), (60, 60, 120, 120))
        self.assertEqual(set(p), set(el.EMOTIONS))
        self.assertAlmostEqual(sum(p.values()), 1.0, places=5)
        self.assertIsNone(b.predict(np.zeros((100, 100, 3), np.uint8), (0, 0, 4, 4)))

    @unittest.skipUnless(has('deepface') and has('onnxruntime') and has('cv2')
                         and os.path.isfile(os.path.expanduser(
                             '~/.deepface/weights/facial_expression_model_weights.onnx')),
                         'chưa cài DeepFace + trọng số (install_emotion_deps.sh)')
    def test_deepface(self):
        self.check('deepface')

    @unittest.skipUnless(has('fer') and has('tensorflow') and has('cv2'), 'chưa cài FER + TensorFlow')
    def test_fer(self):
        self.check('fer')

    def test_unknown_backend(self):
        with self.assertRaises(RuntimeError):
            eb.make_backend('magic', log=lambda m: None)


if __name__ == '__main__':
    unittest.main(verbosity=2)
