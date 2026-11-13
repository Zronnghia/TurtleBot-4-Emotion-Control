#!/usr/bin/env python3
"""Vẽ + đo quỹ đạo của một lần chạy emotion_behavior_node (ảnh và bảng cho báo cáo Bài 8).

  ros2 run tb4_lab04 plot_emotion_run.py                         # lần chạy mới nhất trong ~/tb4_results
  ros2 run tb4_lab04 plot_emotion_run.py ~/tb4_results/emotion_20261112_101500 -o traj.png

Đọc odom.csv -> tách từng lần chạy quỹ đạo (cột active) -> đo: quãng đường, độ dời, góc quay tích luỹ,
độ lệch ngang (trái +/phải −) so với hướng ban đầu, bán kính cung ước lượng. In bảng + ghi summary.csv;
vẽ trajectory.png (màu theo biểu cảm, mũi tên hướng đầu/cuối mỗi quỹ đạo).
"""

import argparse
import csv
import glob
import math
import os
import sys

COLORS = {'happy': '#2ca02c', 'sad': '#1f77b4', 'angry': '#d62728', 'surprise': '#ff7f0e',
          'fear': '#9467bd', 'setup': '#7f7f7f'}
LABELS = {'happy': 'happy – cong trái', 'sad': 'sad – cong phải', 'angry': 'angry – lùi nhẹ',
          'surprise': 'surprise – xoay 1 vòng', 'fear': 'fear – tiến nhẹ', 'setup': 'undock + ra giữa sân'}


def latest_run(root):
    runs = sorted(glob.glob(os.path.join(os.path.expanduser(root), 'emotion_*')))
    runs = [r for r in runs if os.path.isfile(os.path.join(r, 'odom.csv'))]
    return runs[-1] if runs else None


def read_csv(path):
    if not os.path.isfile(path):
        return []
    with open(path, newline='', encoding='utf-8') as f:
        return list(csv.DictReader(f))


def runs_of(rows):
    """[(active, [(t, x, y, yaw)])] – các đoạn liên tiếp cùng 'active' (kể cả rỗng = đứng yên)."""
    out, cur, pts = [], None, []
    for r in rows:
        a = r.get('active') or ''
        t = float(r['sim_t']) if r.get('sim_t') not in (None, '') else float(r['t'])   # giờ mô phỏng nếu có
        p = (t, float(r['x']), float(r['y']), float(r['yaw']))
        if a != cur:
            if pts:
                out.append((cur, pts))
            cur, pts = a, ([pts[-1]] if pts else [])
        pts.append(p)
    if pts:
        out.append((cur, pts))
    return out


def measure(pts):
    """Số đo một quỹ đạo từ các điểm odom (t, x, y, yaw)."""
    t0, x0, y0, th0 = pts[0]
    t1, x1, y1, th1 = pts[-1]
    length = sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(pts, pts[1:]))
    turn = 0.0
    for a, b in zip(pts, pts[1:]):
        d = math.atan2(math.sin(b[3] - a[3]), math.cos(b[3] - a[3]))
        turn += d
    dx, dy = x1 - x0, y1 - y0
    fwd = dx * math.cos(th0) + dy * math.sin(th0)            # + tiến, − lùi (theo hướng ban đầu)
    lat = -dx * math.sin(th0) + dy * math.cos(th0)           # + lệch trái, − lệch phải
    radius = length / abs(turn) if abs(turn) > 0.2 and length > 0.05 else None
    return {'duration': t1 - t0, 'length': length, 'disp': math.hypot(dx, dy), 'forward': fwd,
            'lateral': lat, 'turn_deg': math.degrees(turn), 'radius': radius}


def expected_path(el, gl, emotion, dt=0.01):
    """Quỹ đạo lý thuyết của kế hoạch (động học lý tưởng, tham số mặc định) trong hệ toạ độ robot."""
    plan = el.build_emotion_plan(emotion) or []
    x = y = th = 0.0
    xs, ys = [0.0], [0.0]
    for seg in plan:
        for _ in range(int(round(seg.nominal_duration() / dt))):
            x += seg.lin * math.cos(th) * dt
            y += seg.lin * math.sin(th) * dt
            th += seg.ang * dt
            xs.append(x)
            ys.append(y)
    return xs, ys


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('run', nargs='?', default=None, help='thư mục emotion_<thời_gian>')
    ap.add_argument('-o', '--output', default=None, help='file ảnh (mặc định <run>/trajectory.png)')
    args, _ = ap.parse_known_args(argv)
    run = args.run or latest_run(os.environ.get('TB4_RESULTS_DIR', '~/tb4_results'))
    if not run or not os.path.isdir(os.path.expanduser(run)):
        print('Không tìm thấy thư mục kết quả (chạy emotion_behavior_node trước).')
        return 1
    run = os.path.expanduser(run)
    odom = read_csv(os.path.join(run, 'odom.csv'))
    events = read_csv(os.path.join(run, 'events.csv'))
    if not odom:
        print('odom.csv trống: {}'.format(run))
        return 1
    print('Lần chạy: {} – {} điểm odom, {} sự kiện'.format(run, len(odom), len(events)))
    for e in events:
        if e['type'] in ('start', 'stop', 'setup', 'info') or e['type'] == 'emotion':
            print('  t={:>8}s  {:<8} {:<9} {:<11} {}'.format(e['t'], e['type'], e['emotion'], e['state'],
                                                           e['detail']))
    rows = []
    print('\n(giây = giờ {}; độ dài, độ dời, tiến, trái, r tính bằng m)'.format(
        'mô phỏng/robot' if odom and odom[0].get('sim_t') else 'thực'))
    print('{:<3} {:<9} {:>7} {:>8} {:>8} {:>9} {:>9} {:>9} {:>8}'.format(
        '#', 'quỹ đạo', 'giây', 'đường', 'dời', 'tiến(+)', 'trái(+)', 'quay°', 'r (m)'))
    for active, pts in runs_of(odom):
        if active in ('', None) or active == 'setup' or len(pts) < 2:
            continue
        m = measure(pts)
        m['emotion'] = active
        rows.append(m)
        print('{:<3} {:<9} {:>7.1f} {:>8.3f} {:>8.3f} {:>9.3f} {:>9.3f} {:>9.1f} {:>8}'.format(
            len(rows), active, m['duration'], m['length'], m['disp'], m['forward'], m['lateral'], m['turn_deg'],
            '{:.3f}'.format(m['radius']) if m['radius'] else '-'))
    with open(os.path.join(run, 'summary.csv'), 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['emotion', 'duration_s', 'path_m', 'displacement_m', 'forward_m', 'lateral_left_m',
                    'turn_deg', 'radius_m'])
        for m in rows:
            w.writerow([m['emotion'], '{:.2f}'.format(m['duration']), '{:.3f}'.format(m['length']),
                        '{:.3f}'.format(m['disp']), '{:.3f}'.format(m['forward']), '{:.3f}'.format(m['lateral']),
                        '{:.1f}'.format(m['turn_deg']), '{:.3f}'.format(m['radius']) if m['radius'] else ''])
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        print('Thiếu matplotlib: sudo apt install python3-matplotlib')
        return 1
    fig = plt.figure(figsize=(13, 6.8))
    gs = fig.add_gridspec(2, 4, width_ratios=[1.6, 1, 1, 1], wspace=0.35, hspace=0.45)
    ax = fig.add_subplot(gs[:, 0])
    shown = set()
    order = 0
    for active, pts in runs_of(odom):
        xs, ys = [p[1] for p in pts], [p[2] for p in pts]
        if active in COLORS and active != 'setup' and len(pts) >= 2:
            order += 1                         # số thứ tự quỹ đạo (khớp cột # của bảng)
            mx, my = xs[len(xs) // 2], ys[len(ys) // 2]
            ax.annotate(str(order), xy=(mx, my), xytext=(6, 6), textcoords='offset points', fontsize=9,
                        color=COLORS[active], fontweight='bold')
        if active in COLORS:
            lab = LABELS[active] if active not in shown else None
            shown.add(active)
            if max(xs) - min(xs) < 0.04 and max(ys) - min(ys) < 0.04:      # xoay tại chỗ
                ax.plot([sum(xs) / len(xs)], [sum(ys) / len(ys)], 'o', color=COLORS[active], ms=14,
                        mfc='none', mew=2.5, label=lab)
            else:
                ax.plot(xs, ys, '-', color=COLORS[active], lw=2.4, label=lab)
                _, xe, ye, the = pts[-1]
                ax.annotate('', xy=(xe + 0.08 * math.cos(the), ye + 0.08 * math.sin(the)), xytext=(xe, ye),
                            arrowprops=dict(arrowstyle='->', color=COLORS[active], lw=1.8))
        else:
            ax.plot(xs, ys, '-', color='#bbbbbb', lw=1.0)
    x0, y0 = float(odom[0]['x']), float(odom[0]['y'])
    ax.plot([x0], [y0], 'ks', ms=8, label='Bắt đầu')
    x1, y1 = float(odom[-1]['x']), float(odom[-1]['y'])
    ax.plot([x1], [y1], 'ko', ms=6, label='Kết thúc')
    ax.set_aspect('equal', adjustable='datalim')
    allx = [float(r['x']) for r in odom]
    ally = [float(r['y']) for r in odom]
    cx, cy = (max(allx) + min(allx)) / 2, (max(ally) + min(ally)) / 2
    half = max(0.6, (max(allx) - min(allx)) / 2 + 0.15, (max(ally) - min(ally)) / 2 + 0.15)
    ax.set_xlim(cx - half, cx + half)
    ax.set_ylim(cy - half, cy + half)
    ax.grid(True, alpha=0.3)
    ax.set_xlabel('x (m) – frame odom')
    ax.set_ylabel('y (m)')
    ax.set_title('Toàn bộ lần chạy (số = thứ tự quỹ đạo)')
    ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.1), ncol=2, fontsize=8.5, frameon=False)
    # ---- từng quỹ đạo trong hệ toạ độ của robot lúc bắt đầu (x = hướng mặt robot, y = bên trái)
    sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
    try:
        import emotion_logic as el
        import gesture_logic as gl
    except ImportError:
        el = gl = None
    first = {}
    for active, pts in runs_of(odom):
        if active in COLORS and active != 'setup' and len(pts) >= 2 and active not in first:
            first[active] = pts
    cells = [(0, 1), (0, 2), (0, 3), (1, 1), (1, 2), (1, 3)]
    for (r, c), emo in zip(cells, ('happy', 'sad', 'surprise', 'angry', 'fear')):
        a = fig.add_subplot(gs[r, c])
        a.set_title(LABELS[emo], fontsize=9.5, color=COLORS[emo])
        if el is not None:                     # quỹ đạo lý thuyết (động học lý tưởng)
            ex, ey = expected_path(el, gl, emo)
            a.plot(ex, ey, '--', color='k', lw=1, alpha=0.6, label='lý thuyết')
        if emo in first:
            t0, xs0, ys0, th0 = first[emo][0]
            lx, ly, lth = [], [], []
            for _, x, y, th in first[emo]:
                dx, dy = x - xs0, y - ys0
                lx.append(dx * math.cos(th0) + dy * math.sin(th0))
                ly.append(-dx * math.sin(th0) + dy * math.cos(th0))
                lth.append(th - th0)
            if max(map(abs, lx + ly)) < 0.03:
                a.plot([0], [0], 'o', color=COLORS[emo], ms=16, mfc='none', mew=2.5, label='đo /odom')
                m = measure(first[emo])
                a.text(0, -0.17, 'quay {:.1f}°'.format(m['turn_deg']), ha='center', fontsize=9)
            else:
                a.plot(lx, ly, '-', color=COLORS[emo], lw=2.4, label='đo /odom')
                a.annotate('', xy=(lx[-1] + 0.06 * math.cos(lth[-1]), ly[-1] + 0.06 * math.sin(lth[-1])),
                           xytext=(lx[-1], ly[-1]), arrowprops=dict(arrowstyle='->', color=COLORS[emo], lw=1.6))
        else:
            a.text(0, 0.2, '(chưa chạy)', ha='center', fontsize=9, color='#888888')
        a.annotate('', xy=(0.1, 0), xytext=(0, 0), arrowprops=dict(arrowstyle='->', color='k', lw=1.2))
        a.plot([0], [0], 'ks', ms=5)
        a.set_xlim(-0.35, 0.45)
        a.set_ylim(-0.4, 0.4)
        a.set_aspect('equal')
        a.grid(True, alpha=0.3)
        a.tick_params(labelsize=7)
        if r == 1:
            a.set_xlabel('tiến (m)', fontsize=8)
        if c == 1:
            a.set_ylabel('trái (m)', fontsize=8)
    leg = fig.add_subplot(gs[1, 3])
    leg.axis('off')
    leg.plot([], [], '--', color='k', label='lý thuyết (kế hoạch)')
    leg.plot([], [], '-', color='#555555', lw=2.4, label='đo bằng /odom')
    leg.plot([], [], 'ks', label='vị trí + hướng ban đầu')
    leg.legend(loc='center', fontsize=9, frameon=False)
    fig.suptitle('Quỹ đạo TurtleBot 4 điều khiển bằng biểu cảm khuôn mặt', fontsize=13)
    out = args.output or os.path.join(run, 'trajectory.png')
    fig.savefig(out, dpi=150, bbox_inches='tight')
    print('\nĐã vẽ: {}\nBảng số đo: {}'.format(out, os.path.join(run, 'summary.csv')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
