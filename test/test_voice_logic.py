#!/usr/bin/env python3
"""Unit test Bài 7: phân vùng bản đồ, phân tích câu lệnh tiếng Việt, lộ trình, VAD (không cần ROS chạy).

    cd ~/workspaces/tb4_gazebo/src/tb4_lab04 && python3 -m pytest test/test_voice_logic.py -q
"""
import importlib.util
import math
import os
import struct
import sys
import tempfile
import unittest
import wave

import numpy as np
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, 'scripts'))


def load(rel_path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel_path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


zs = load('scripts/zone_segmentation.py', 'zone_segmentation')
vc = load('scripts/voice_command.py', 'voice_command')
sr = load('scripts/speech_recognizer_node.py', 'speech_recognizer_node')
vn = load('scripts/voice_navigator.py', 'voice_navigator')
ab = load('scripts/asr_benchmark.py', 'asr_benchmark')
cg = load('scripts/check_goals.py', 'check_goals')

MAP = os.path.join(ROOT, 'maps', 'map.yaml')
NAMES = os.path.join(ROOT, 'config', 'zone_names.yaml')
OBJECTS = os.path.join(ROOT, 'config', 'objects.yaml')
MANUAL = os.path.join(ROOT, 'config', 'zones_manual.yaml')


def write_map(tmp, pixels, res=0.05, origin=(0.0, 0.0, 0.0)):
    h, w = pixels.shape
    with open(os.path.join(tmp, 'm.pgm'), 'wb') as f:
        f.write('P5\n{} {}\n255\n'.format(w, h).encode())
        f.write(pixels.astype(np.uint8).tobytes())
    path = os.path.join(tmp, 'm.yaml')
    with open(path, 'w') as f:
        yaml.safe_dump({'image': 'm.pgm', 'resolution': res, 'origin': list(origin), 'negate': 0,
                        'occupied_thresh': 0.65, 'free_thresh': 0.15, 'mode': 'trinary'}, f)
    return path


def two_rooms_map(tmp):
    """Hai phòng 4 m x 4 m nối nhau bằng một cửa rộng 0.9 m (ảnh: hàng 0 = mép trên)."""
    res = 0.05
    w, h = int(9.0 / res), int(4.4 / res)
    img = np.full((h, w), 0, np.uint8)                   # tường
    img[4:h - 4, 4:int(4.2 / res)] = 254                  # phòng trái  x 0.2..4.2
    img[4:h - 4, int(4.8 / res):w - 4] = 254              # phòng phải  x 4.8..8.8
    door = slice(int(1.75 / res), int(2.65 / res))        # cửa 0.9 m ở giữa
    img[door, int(4.2 / res):int(4.8 / res)] = 254
    return write_map(tmp, img, res)


ZONES_FIXTURE = [
    {'id': 'A', 'name': 'Phòng học', 'aliases': ['lớp học'], 'goal': {'x': 0, 'y': 0, 'yaw': None}},
    {'id': 'B', 'name': 'Khu vực B', 'aliases': [], 'goal': {'x': 1, 'y': 0, 'yaw': None}},
    {'id': 'C', 'name': 'Khu vực C', 'aliases': [], 'goal': {'x': 2, 'y': 0, 'yaw': None}},
    {'id': 'D', 'name': 'Phòng thí nghiệm', 'aliases': ['phòng lab'], 'goal': {'x': 3, 'y': 0, 'yaw': None}},
    {'id': 'E', 'name': 'Hành lang', 'aliases': [], 'goal': {'x': 4, 'y': 0, 'yaw': 1.0}},
]


# ===================================================================================== phân vùng
class TestSegmentationSynthetic(unittest.TestCase):
    def test_two_rooms_split_at_door(self):
        with tempfile.TemporaryDirectory() as tmp:
            gm = cg.GridMap(two_rooms_map(tmp))
            res = zs.segment(gm, start_xy=(2.0, 2.2), params={'min_area': 2.0})
            self.assertEqual(len(res['zones']), 2)
            left, right = sorted(res['zones'], key=lambda z: z['center'][0])
            self.assertLess(left['center'][0], 4.5)
            self.assertGreater(right['center'][0], 4.5)
            for z in res['zones']:
                self.assertTrue(z['valid'], z)
                self.assertAlmostEqual(z['area_m2'], 16.0, delta=2.0)
                self.assertGreaterEqual(z['goal_clearance_m'], 0.5)
            self.assertEqual(left['neighbors'], [right['id']])
            # ranh giới nằm quanh cửa (x ~ 4.2..4.8)
            lab = res['labels']
            j = int(2.2 / gm.res)
            row = lab[j, :]
            change = [i for i in range(1, len(row)) if row[i] >= 0 and row[i - 1] >= 0 and row[i] != row[i - 1]]
            self.assertEqual(len(change), 1)
            self.assertTrue(3.9 <= change[0] * gm.res <= 5.1, change[0] * gm.res)

    def test_wide_opening_is_one_room(self):
        """Không có chỗ thắt (cửa rộng bằng phòng) -> 1 vùng (không chia vụn)."""
        with tempfile.TemporaryDirectory() as tmp:
            res_m = 0.05
            img = np.zeros((int(4.4 / res_m), int(9.0 / res_m)), np.uint8)
            img[4:-4, 4:-4] = 254
            gm = cg.GridMap(write_map(tmp, img, res_m))
            res = zs.segment(gm, start_xy=(2.0, 2.2))
            self.assertEqual(len(res['zones']), 1)

    def test_unreachable_space_excluded(self):
        """Phòng kín không có cửa -> không phải khu vực (robot không tới được)."""
        with tempfile.TemporaryDirectory() as tmp:
            res_m = 0.05
            img = np.zeros((int(4.4 / res_m), int(9.0 / res_m)), np.uint8)
            img[4:-4, 4:int(4.2 / res_m)] = 254
            img[4:-4, int(4.8 / res_m):-4] = 254           # không có cửa
            gm = cg.GridMap(write_map(tmp, img, res_m))
            res = zs.segment(gm, start_xy=(2.0, 2.2), params={'min_area': 2.0})
            self.assertEqual(len(res['zones']), 1)
            self.assertLess(res['zones'][0]['center'][0], 4.5)

    def test_letter_ids(self):
        self.assertEqual([zs.letter_id(k) for k in (0, 1, 25, 26, 27)], ['A', 'B', 'Z', 'AA', 'AB'])

    def test_merge_small_regions(self):
        lab = np.full((10, 30), -1, np.int32)
        lab[:, 0:12] = 0
        lab[:, 12:14] = 1          # mảnh nhỏ kẹp giữa
        lab[:, 14:30] = 2
        out = zs.merge_small_regions(lab, min_cells=40)
        self.assertEqual(len(np.unique(out[out >= 0])), 2)

    def test_point_in_polygon(self):
        sq = [[0, 0], [2, 0], [2, 2], [0, 2]]
        self.assertTrue(zs.point_in_polygon(1, 1, sq))
        self.assertFalse(zs.point_in_polygon(3, 1, sq))


class TestSegmentationRealMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gm = cg.GridMap(MAP)
        cls.objects = cg.load_objects(OBJECTS)
        cls.res = zs.segment(cls.gm, (0.0, 0.0), cls.objects, zs.load_names(NAMES))

    def test_at_least_three_valid_labelled_zones(self):
        zones = self.res['zones']
        self.assertGreaterEqual(len(zones), 3)
        self.assertTrue(all(z['valid'] for z in zones), [z['id'] for z in zones if not z['valid']])
        named = [z for z in zones if z['name'] != 'Khu vực ' + z['id']]
        self.assertGreaterEqual(len(named), 3)
        names = {z['name'] for z in zones}
        for n in ('Phòng học', 'Phòng thí nghiệm', 'Hành lang', 'Sảnh chính'):
            self.assertIn(n, names)

    def test_goals_free_clear_reachable(self):
        passable = self.res['reach']
        for z in self.res['zones']:
            g = z['goal']
            i, j = self.gm.to_cell(g['x'], g['y'])
            self.assertEqual(self.gm.occ[j, i], 0, z['id'])
            self.assertGreaterEqual(z['goal_clearance_m'], 0.5, z['id'])
            self.assertTrue(passable[j, i], z['id'])
            self.assertIsNotNone(z['path_from_start_m'], z['id'])
            if 'goal_object_distance_m' in z:
                self.assertGreater(z['goal_object_distance_m'], 0.4, z['id'])
            # điểm đích nằm trong chính khu vực đó
            self.assertEqual(self.res['labels'][j, i], z['index'])

    def test_start_is_in_main_hall(self):
        i, j = self.gm.to_cell(0.0, 0.0)
        k = self.res['labels'][j, i]
        self.assertGreaterEqual(k, 0)

    def test_deterministic(self):
        again = zs.segment(self.gm, (0.0, 0.0), self.objects, zs.load_names(NAMES))
        self.assertEqual([z['goal'] for z in again['zones']], [z['goal'] for z in self.res['zones']])
        self.assertTrue((again['labels'] == self.res['labels']).all())

    def test_save_and_reload_zonemap(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, 'zones.yaml')
            zs.save_zones(out, self.gm, self.res, MAP, 'test', (0, 0))
            zm = zs.ZoneMap(out)
            self.assertEqual(len(zm.zones), len(self.res['zones']))
            for z in zm.zones:
                self.assertEqual(zm.zone_at(z['goal']['x'], z['goal']['y']), z['id'])
            # điểm trong tường cạnh một khu vực -> vùng gần nhất; điểm ngoài bản đồ -> None
            self.assertIsNone(zm.zone_at(100.0, 100.0))
            # không có ảnh nhãn -> dùng đa giác
            os.remove(os.path.join(tmp, 'zones_labels.pgm'))
            zm2 = zs.ZoneMap(out)
            hits = sum(zm2.zone_at(z['goal']['x'], z['goal']['y']) == z['id'] for z in zm2.zones)
            self.assertGreaterEqual(hits, len(zm2.zones) - 1)

    def test_committed_zones_file_matches_map(self):
        """maps/zones.yaml trong repo phải khớp với bản đồ + zone_names.yaml hiện tại."""
        path = os.path.join(ROOT, 'maps', 'zones.yaml')
        zm = zs.ZoneMap(path)
        self.assertEqual([(z['id'], z['name']) for z in zm.zones],
                         [(z['id'], z['name']) for z in self.res['zones']])

    def test_manual_mode(self):
        res = zs.segment(self.gm, (0.0, 0.0), self.objects, (), zs.load_manual(MANUAL))
        self.assertEqual(len(res['zones']), 4)
        self.assertTrue(all(z['valid'] for z in res['zones']))
        self.assertIn('Phòng thí nghiệm', [z['name'] for z in res['zones']])

    def test_duplicate_anchor_rejected(self):
        names = [{'anchor': (-6.3, 7.9), 'name': 'X', 'aliases': [], 'yaw': None},
                 {'anchor': (-6.0, 7.5), 'name': 'Y', 'aliases': [], 'yaw': None}]
        with self.assertRaises(ValueError):
            zs.segment(self.gm, (0.0, 0.0), (), names)

    def test_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = zs.main(['--out', os.path.join(tmp, 'z.yaml'), '--plot', os.path.join(tmp, 'z.png')])
            self.assertEqual(code, 0)
            self.assertTrue(os.path.isfile(os.path.join(tmp, 'z_labels.pgm')))


# ===================================================================================== câu lệnh
class TestParser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = vc.ZoneCatalog(ZONES_FIXTURE)

    def p(self, text):
        return vc.parse_command(text, self.cat)

    def test_spec_examples(self):
        c = self.p('Đi đến khu vực A.')
        self.assertEqual((c.intent, c.start, c.targets), ('navigate', None, ['A']))
        c = self.p('Di chuyển từ khu vực A đến khu vực B.')
        self.assertEqual((c.intent, c.start, c.targets), ('navigate', 'A', ['B']))
        c = self.p('Đi đến phòng thí nghiệm.')
        self.assertEqual((c.intent, c.targets), ('navigate', ['D']))

    def test_multi_waypoint(self):
        c = self.p('Đi từ phòng A qua hành lang C rồi đến phòng B')
        self.assertEqual((c.start, c.targets), ('A', ['C', 'B']))
        c = self.p('đi đến khu vực A, khu vực B rồi khu vực C')
        self.assertEqual(c.targets, ['A', 'B', 'C'])
        c = self.p('đi từ A đến B')
        self.assertEqual((c.start, c.targets), ('A', ['B']))

    def test_variants(self):
        for text, target in [('di den khu vuc a', 'A'), ('DI CHUYỂN TỚI KHU B!!!', 'B'),
                             ('robot ơi, đi tới lớp học nhé', 'A'), ('tôi muốn đi tới phòng lab', 'D'),
                             ('toi muon di toi phong hoc', 'A'), ('đi đến khu vực bê', 'B'),
                             ('đi đến khu vực xê', 'C'), ('đi đến khu vực đê', 'D'),
                             ('về hành lang', 'E'), ('đi đến khu vực A ạ', 'A'),
                             ('go to zone C', 'C')]:
            c = self.p(text)
            self.assertEqual((c.intent, c.targets), ('navigate', [target]), text)

    def test_asr_typo_fuzzy(self):
        c = self.p('đi đến phòng thí nhiệm')
        self.assertEqual(c.targets, ['D'])
        self.assertEqual(c.fuzzy, ['D'])

    def test_unknown_zone_rejected(self):
        for text, unk in [('Đi đến khu vực Z', 'khu vực z'), ('khu vực M', 'khu vực m'),
                          ('đi tới nhà bếp', 'nhà bếp'), ('đi đến phòng ăn rồi về khu vực A', 'phòng ăn')]:
            c = self.p(text)
            self.assertEqual(c.intent, 'invalid', text)
            self.assertEqual(c.targets, [], text)
            self.assertIn(unk, ' '.join(c.unknown) + ' ' + c.message.lower(), text)
            self.assertIn('Các khu vực hiện có', c.message)

    def test_letter_zone_never_fuzzy(self):
        """'khu vực Z' giống 'khu vực C' về chữ nhưng là khu vực KHÁC -> không được đoán."""
        c = self.p('đi đến khu vực Z')
        self.assertEqual(c.intent, 'invalid')
        self.assertNotIn('C', c.targets)

    def test_no_zone(self):
        for text in ('xin chào', 'đi đến', 'nhà bếp', ''):
            c = self.p(text)
            self.assertIn(c.intent, ('invalid', 'empty'), text)
            self.assertEqual(plan := vc.plan_route(c, 'A'), [], plan)

    def test_stop_list_where(self):
        for t in ('dừng lại', 'Huỷ!', 'stop', 'dung lai'):
            self.assertEqual(self.p(t).intent, 'stop', t)
        self.assertEqual(self.p('có những khu vực nào?').intent, 'list')
        self.assertEqual(self.p('tôi đang ở đâu').intent, 'where')
        self.assertEqual(self.p('đi đến khu vực A rồi dừng lại').targets, ['A'])

    def test_asr_noise_before_zone_name(self):
        """Whisper nghe "đến" thành "bên"/"biến" nhưng đúng tên khu vực -> vẫn hiểu đúng đích (đã gặp)."""
        for text, zid in [('Bên phòng thí nghiệm.', 'D'), ('Đi biến phòng học.', 'A'), ('bên hành lang', 'E')]:
            c = self.p(text)
            self.assertEqual((c.intent, c.targets), ('navigate', [zid]), text)

    def test_stop_asr_variants(self):
        for t in ('Vũng lại.', 'rừng lại', 'dừng lại ngay'):
            self.assertEqual(self.p(t).intent, 'stop', t)

    def test_same_start_and_target_rejected(self):
        c = self.p('đi từ phòng lab đến phòng thí nghiệm')
        self.assertEqual(c.intent, 'invalid')

    def test_from_without_destination(self):
        c = self.p('đi từ khu vực A')
        self.assertEqual(c.intent, 'invalid')

    def test_tôi_is_not_tới(self):
        c = self.p('tôi muốn đi đến khu vực C')
        self.assertEqual((c.intent, c.targets), ('navigate', ['C']))

    def test_real_catalog(self):
        cat = vc.ZoneCatalog(zs.ZoneMap(os.path.join(ROOT, 'maps', 'zones.yaml')).zones)
        for text, zid in [('đi đến phòng học', 'A'), ('đi đến phòng thí nghiệm', 'I'), ('về trạm sạc', 'F'),
                          ('đi tới khu vực L', 'L'), ('đi tới thư viện', 'K')]:
            self.assertEqual(vc.parse_command(text, cat).targets, [zid], text)


class TestAsrBenchmark(unittest.TestCase):
    def test_judge(self):
        cat = vc.ZoneCatalog(ZONES_FIXTURE)
        j = lambda text, item: ab.judge(vc.parse_command(text, cat), item)  # noqa: E731
        self.assertEqual(j('đi đến khu vực A', {'expect': 'navigate', 'targets': ['A']}), 'ĐÚNG')
        self.assertEqual(j('đi đến khu vực B', {'expect': 'navigate', 'targets': ['A']}), 'ĐI NHẦM')
        self.assertEqual(j('xin chào', {'expect': 'navigate', 'targets': ['A']}), 'SAI')
        self.assertEqual(j('đi đến khu vực Z', {'expect': 'invalid'}), 'ĐÚNG')
        self.assertEqual(j('đi đến khu vực A', {'expect': 'invalid'}), 'ĐI NHẦM')
        self.assertEqual(j('từ khu vực A đến khu vực B', {'expect': 'navigate', 'start': 'A', 'targets': ['B']}),
                         'ĐÚNG')

    def test_sentence_file_matches_zones(self):
        """Câu mẫu của asr_benchmark khớp maps/zones.yaml hiện tại (gõ đúng chữ -> phải ĐÚNG hết)."""
        items = ab.load_sentences(os.path.join(ROOT, 'config', 'asr_test_sentences.yaml'))
        cat = vc.ZoneCatalog(zs.ZoneMap(os.path.join(ROOT, 'maps', 'zones.yaml')).zones)
        self.assertGreaterEqual(len(items), 10)
        for it in items:
            self.assertEqual(ab.judge(vc.parse_command(it['text'], cat), it), 'ĐÚNG', it['text'])


class TestRoute(unittest.TestCase):
    def setUp(self):
        self.cat = vc.ZoneCatalog(ZONES_FIXTURE)

    def route(self, text, here):
        return vc.plan_route(vc.parse_command(text, self.cat), here)

    def test_from_a_to_b(self):
        self.assertEqual(self.route('di chuyển từ khu vực A đến khu vực B', 'A'), ['B'])
        self.assertEqual(self.route('di chuyển từ khu vực A đến khu vực B', 'C'), ['A', 'B'])
        self.assertEqual(self.route('di chuyển từ khu vực A đến khu vực B', None), ['A', 'B'])

    def test_simple_and_multi(self):
        self.assertEqual(self.route('đi đến khu vực C', 'A'), ['C'])
        self.assertEqual(self.route('đi từ phòng A qua hành lang C rồi đến phòng B', 'E'), ['A', 'C', 'B'])
        self.assertEqual(self.route('đi đến khu vực A rồi khu vực A rồi khu vực B', 'C'), ['A', 'B'])

    def test_leg_yaw(self):
        self.assertAlmostEqual(vn.leg_yaw({'x': 1.0, 'y': 1.0, 'yaw': None}, (0.0, 0.0)), math.pi / 4)
        self.assertEqual(vn.leg_yaw({'x': 1.0, 'y': 1.0, 'yaw': 0.5}, (0.0, 0.0)), 0.5)
        self.assertEqual(vn.leg_yaw({'x': 1.0, 'y': 1.0, 'yaw': None}, None), 0.0)
        self.assertEqual(vn.hex_rgb('#ff0000'), (1.0, 0.0, 0.0))


# ===================================================================================== âm thanh
def tone(sec, amp, rate=16000, f=440.0):
    return [amp * math.sin(2 * math.pi * f * k / rate) for k in range(int(sec * rate))]


class TestAudio(unittest.TestCase):
    def test_vad_segments_two_utterances(self):
        vad = sr.EnergyVAD(threshold=0.05, min_speech=0.3, end_silence=0.5)
        sig = tone(0.5, 0.0) + tone(1.0, 0.3) + tone(0.8, 0.001) + tone(0.6, 0.3) + tone(1.0, 0.0)
        utts = []
        for k in range(0, len(sig), 1600):
            utts += vad.feed(sig[k:k + 1600])
        self.assertEqual(len(utts), 2)
        self.assertAlmostEqual(len(utts[0]) / 16000.0, 1.0 + 0.5 + 0.3, delta=0.35)

    def test_vad_drops_clicks_and_calibrates(self):
        vad = sr.EnergyVAD(threshold=0.0, min_speech=0.3, end_silence=0.5, calib=1.0)
        sig = tone(1.0, 0.01) + tone(0.12, 0.5) + tone(1.0, 0.01)
        utts = vad.feed(sig)
        self.assertAlmostEqual(vad.threshold, 3 * 0.01 / math.sqrt(2), delta=0.01)
        self.assertEqual(utts, [])
        self.assertIsNone(vad.flush())

    def test_vad_max_speech(self):
        vad = sr.EnergyVAD(threshold=0.05, max_speech=2.0)
        self.assertEqual(len(vad.feed(tone(5.0, 0.3))), 2)

    def test_wav_roundtrip_resample(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'a.wav')
            data = tone(0.5, 0.4, rate=44100)
            with wave.open(path, 'wb') as w:
                w.setnchannels(2)
                w.setsampwidth(2)
                w.setframerate(44100)
                frames = b''.join(struct.pack('<hh', int(s * 32767), int(s * 32767)) for s in data)
                w.writeframes(frames)
            out = sr.read_wav(path, 16000)
            self.assertAlmostEqual(len(out), 8000, delta=2)
            self.assertAlmostEqual(sr.rms(out), 0.4 / math.sqrt(2), delta=0.02)

    def test_pcm_roundtrip(self):
        x = [0.0, 0.5, -0.5, 0.999]
        y = sr.pcm16_to_floats(sr.floats_to_pcm16(x))
        for a, b in zip(x, y):
            self.assertAlmostEqual(a, b, delta=1e-3)

    def test_grammar_and_prompt(self):
        g = sr.vosk_grammar(ZONES_FIXTURE)
        self.assertIn('khu vực a', g)
        self.assertIn('khu vực bê', g)
        self.assertIn('phòng thí nghiệm', g)
        self.assertEqual(g[-1], '[unk]')
        self.assertEqual(len(g), len(set(g)))
        prompt = sr.whisper_prompt(ZONES_FIXTURE)
        self.assertIn('phòng thí nghiệm', prompt)
        self.assertNotIn('Đi đến', prompt)            # không có câu lệnh mẫu (Whisper sẽ chép lại)
        self.assertIsNone(sr.whisper_prompt(ZONES_FIXTURE, 'none'))
        self.assertEqual(sr.whisper_prompt(ZONES_FIXTURE, 'abc'), 'abc')
        self.assertEqual(sr.clean_text(' đi  [unk] đến '), 'đi không rõ đến')
        self.assertEqual(sr.clean_text('[unk] [unk]'), '')

    def test_vosk_unk_zone_is_rejected(self):
        """Grammar Vosk: "khu vực Z" -> "khu vực [unk]" -> phải báo khu vực không tồn tại, robot đứng yên."""
        cat = vc.ZoneCatalog(ZONES_FIXTURE)
        c = vc.parse_command(sr.clean_text('đi đến khu vực [unk]'), cat)
        self.assertEqual(c.intent, 'invalid')
        self.assertEqual(c.targets, [])

    def test_hallucination_guard(self):
        prompt = 'Robot di chuyển trong tòa nhà có phòng học, hành lang, sảnh chính, thư viện.'
        bad = ['Robot di chuyển trong tòa nhà', 'phòng học, hành lang',          # chép nguyên văn
               'Đi thư phòng học, hành lang, sảnh chính, phòng thư viện.',      # chép đoạn dài (đã gặp)
               'B, B, B, B.', 'đi đi đi đi', 'khu vực khu vực khu vực',
               'Đi chuyển từ phòng thí nghiệm, phòng thí nghiệm.']               # lặp cụm (đã gặp)
        for t in bad:
            self.assertIsNotNone(sr.suspicious_transcript(t, prompt), t)
        good = ['Đi đến phòng học.', 'Đi đến khu vực A.', 'đi từ phòng học qua hành lang rồi đến thư viện',
                'Di chuyển từ sảnh chính đến khu vực C', 'dừng lại', 'đi đến khu vực A, khu vực B rồi khu vực C']
        for t in good:
            self.assertIsNone(sr.suspicious_transcript(t, prompt), t)
            self.assertIsNone(sr.suspicious_transcript(t, None), t)


if __name__ == '__main__':
    unittest.main()
