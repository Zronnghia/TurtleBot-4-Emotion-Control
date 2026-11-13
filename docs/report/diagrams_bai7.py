#!/usr/bin/env python3
"""Vẽ sơ đồ cho báo cáo Bài 7 -> docs/report/fig/fig7_pipeline.png, fig7_segmentation.png.

    python3 docs/report/diagrams_bai7.py
"""
import os
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIG = os.path.join(HERE, 'fig')
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
plt.rcParams['font.family'] = 'DejaVu Sans'


def box(ax, x, y, w, h, title, sub, color):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle='round,pad=0.02,rounding_size=0.08', fc=color, ec='#333333',
                                lw=1.0))
    ax.text(x + w / 2, y + h * 0.66, title, ha='center', va='center', fontsize=9.5, weight='bold')
    ax.text(x + w / 2, y + h * 0.30, sub, ha='center', va='center', fontsize=7.6, color='#222222')


def arrow(ax, x0, y0, x1, y1, label=''):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle='-|>', mutation_scale=12, lw=1.1, color='#333333'))
    if label:
        ax.text((x0 + x1) / 2, max(y0, y1) + 0.55, label, ha='center', va='bottom', fontsize=7.2,
                family='DejaVu Sans Mono', color='#1f4e79')


def pipeline(out):
    fig, ax = plt.subplots(figsize=(10.0, 3.6))
    ax.set_xlim(0, 10.0)
    ax.set_ylim(0, 3.6)
    ax.axis('off')
    w, h = 1.75, 0.95
    y1 = 2.05
    box(ax, 0.1, y1, w, h, 'Micro / WAV', '16 kHz mono', '#e8f1fb')
    box(ax, 2.45, y1, w, h, 'speech_recognizer', 'Vosk (vi) | Whisper\nVAD năng lượng', '#d9ead3')
    box(ax, 4.8, y1, w, h, 'voice_command', 'chuẩn hoá, khớp tên\nvai trò từ/đến/qua', '#fff2cc')
    box(ax, 7.15, y1, 2.7, h, 'voice_navigator', 'khu vực hiện tại -> lộ trình\nundock, gửi từng chặng', '#fce5cd')
    arrow(ax, 0.1 + w, y1 + h / 2, 2.45, y1 + h / 2)
    arrow(ax, 2.45 + w, y1 + h / 2, 4.8, y1 + h / 2, '/voice/text')
    arrow(ax, 4.8 + w, y1 + h / 2, 7.15, y1 + h / 2, 'start, targets')
    y0 = 0.25
    box(ax, 0.1, y0, w, h, 'map.pgm + map.yaml', 'occupancy grid (SLAM)', '#e8f1fb')
    box(ax, 2.45, y0, w + 0.6, h, 'zone_segmentation', 'distance transform\n+ watershed persistence', '#d9ead3')
    box(ax, 5.4, y0, w - 0.2, h, 'zones.yaml', 'ID, tên, đích\nzones_labels.pgm', '#fff2cc')
    box(ax, 7.15, y0, 2.7, h, 'Nav2 (bt_navigator)', 'NavigateToPose, AMCL\nplanner + DWB tránh vật cản', '#ead1dc')
    arrow(ax, 0.1 + w, y0 + h / 2, 2.45, y0 + h / 2)
    arrow(ax, 2.45 + w + 0.6, y0 + h / 2, 5.4, y0 + h / 2)
    arrow(ax, 5.4 + w - 0.2, y0 + h / 2 + 0.2, 7.3, y1 + 0.05)
    arrow(ax, 8.5, y1, 8.5, y0 + h)
    ax.text(8.58, (y1 + y0 + h) / 2, 'NavigateToPose', ha='left', va='center', fontsize=7.2,
            family='DejaVu Sans Mono', color='#1f4e79')
    ax.text(9.9, y0 + h + 0.18, 'Gazebo / TurtleBot 4', ha='right', fontsize=7.2, color='#666666')
    fig.tight_layout(pad=0.1)
    fig.savefig(out, dpi=170)
    plt.close(fig)


def segmentation_steps(out):
    """Minh hoạ: distance transform + kết quả watershed trên bản đồ thật."""
    import check_goals as cg
    import zone_segmentation as zs
    gm = cg.GridMap(os.path.join(ROOT, 'maps', 'map.yaml'))
    res = zs.segment(gm, (0.0, 0.0), cg.load_objects(os.path.join(ROOT, 'config', 'objects.yaml')),
                     zs.load_names(os.path.join(ROOT, 'config', 'zone_names.yaml')))
    dist = zs.clearance_field(~res['free'], gm.res)
    fig, axs = plt.subplots(1, 2, figsize=(10.0, 4.8))
    d = np.where(res['free'], dist, np.nan)
    im = axs[0].imshow(d, origin='lower', extent=gm.extent(), cmap='viridis')
    axs[0].set_title('(a) Distance transform (m) – đỉnh = tâm phòng', fontsize=10)
    fig.colorbar(im, ax=axs[0], fraction=0.046, pad=0.02)
    from matplotlib.colors import to_rgb
    img = np.full(gm.occ.shape + (3,), 0.80)
    img[gm.occ == 0] = 1.0
    img[gm.occ == 100] = 0.1
    for z in res['zones']:
        img[res['labels'] == z['index']] = np.array(to_rgb(zs.PALETTE[z['index'] % len(zs.PALETTE)])) * 0.6 + 0.4
    axs[1].imshow(img, origin='lower', extent=gm.extent(), interpolation='nearest')
    for z in res['zones']:
        g = z['goal']
        axs[1].plot(g['x'], g['y'], 'o', ms=5, color='k')
        axs[1].text(g['x'], g['y'] + 0.45, z['id'], ha='center', fontsize=9, weight='bold')
    axs[1].set_title('(b) Watershed + gộp: {} khu vực, chấm = điểm đích'.format(len(res['zones'])), fontsize=10)
    for ax in axs:
        ax.set_xticks(range(-10, 11, 5))
        ax.set_yticks(range(-10, 11, 5))
        ax.tick_params(labelsize=8)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    os.makedirs(FIG, exist_ok=True)
    pipeline(os.path.join(FIG, 'fig7_pipeline.png'))
    segmentation_steps(os.path.join(FIG, 'fig7_segmentation.png'))
    print('Đã vẽ: fig/fig7_pipeline.png, fig/fig7_segmentation.png')
