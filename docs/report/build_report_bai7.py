#!/usr/bin/env python3
"""Dựng báo cáo NGẮN (2 trang) Bài 7 "Phân vùng bản đồ và điều hướng TurtleBot 4 bằng giọng nói".

    python3 docs/report/diagrams_bai7.py        # vẽ lại sơ đồ (fig/fig7_*.png) – chỉ khi sửa bản đồ / thuật toán
    python3 docs/report/build_report_bai7.py    # -> docs/report/BaoCao_Bai7_TurtleBot4_Voice.pdf

Bảng kết quả thử nghiệm dựng TỰ ĐỘNG từ file voice_run.json do voice_navigator.py lưu:
  * docs/report_info.yaml -> voice_run: ~/tb4_results/voice_<thời_gian>/voice_run.json   (lần chạy CỦA BẠN)
  * không điền -> docs/report/fig/test7_voice_run.json (lần chạy kiểm thử trong môi trường ảo; script in CẢNH BÁO)
Ảnh của bạn (thiếu thì dùng ảnh kiểm thử + CẢNH BÁO): docs/report/fig_user/voice_run.png
(`zone_segmentation.py --run <voice_run.json>`). Link: docs/report_info.yaml (link_video, link_github).
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_report as br  # noqa: E402  (phông, kiểu chữ, bảng, hình – dùng chung với báo cáo bài 5, 6)
from build_report import M, cm  # noqa: E402
from reportlab.lib.enums import TA_CENTER  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import ParagraphStyle  # noqa: E402
from reportlab.platypus import Paragraph  # noqa: E402

FIG = os.path.join(HERE, 'fig')
USER = os.path.join(HERE, 'fig_user')
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(HERE, 'BaoCao_Bai7_TurtleBot4_Voice.pdf')
TITLE = 'Báo cáo thực hành số 7 – Phân vùng bản đồ và điều hướng TurtleBot 4 bằng giọng nói'
WARN = []

title_st = ParagraphStyle('t7', fontName='Sans-B', fontSize=13.5, leading=17, alignment=TA_CENTER,
                          textColor=br.BLUE, spaceAfter=2)
sub_st = ParagraphStyle('s7', fontName='Serif', fontSize=10, leading=13, alignment=TA_CENTER, spaceAfter=6)
small = ParagraphStyle('p7', parent=br.body, fontSize=10, leading=13.0, spaceAfter=2.5, firstLineIndent=0)
h2c = ParagraphStyle('h2c', parent=br.h2, fontSize=11, spaceBefore=6, spaceAfter=3)


def p(text):
    return Paragraph(text, small)


def h(text):
    return Paragraph(text, h2c)


def link(url):
    url = (url or '').strip()
    if not url:
        br.MISSING.append('link trong docs/report_info.yaml')
        return '<font color="#b22222">(chưa điền – docs/report_info.yaml)</font>'
    return '<link href="{0}" color="blue"><u>{0}</u></link>'.format(br.esc(url))


def pick(user_name, test_path):
    u = os.path.join(USER, user_name)
    if os.path.isfile(u):
        return u, ''
    WARN.append(user_name)
    return test_path, ' (lần chạy kiểm thử trong môi trường ảo)'


def load_run(info):
    path = os.path.expanduser(str(info.get('voice_run') or '').strip())
    note = ''
    if not path or not os.path.isfile(path):
        if path:
            print('KHÔNG thấy voice_run: {} – dùng file kiểm thử'.format(path))
        path = os.path.join(FIG, 'test7_voice_run_asr.json')
        note = ' <i>(kiểm thử trong môi trường ảo: 4 câu đầu qua Whisper thật – model base, file WAV giọng máy '\
               'espeak-ng; 2 câu cuối gõ phím. Thay bằng lần chạy của bạn: voice_run trong docs/report_info.yaml)</i>'
        WARN.append('voice_run (bảng kết quả)')
    with open(path, encoding='utf-8') as f:
        return json.load(f), note


def zone_names():
    import yaml
    with open(os.path.join(ROOT, 'maps', 'zones.yaml'), encoding='utf-8') as f:
        zones = yaml.safe_load(f)['zones']
    return {z['id']: z['name'] for z in zones}, zones


def result_rows(run, names):
    """Mỗi câu lệnh -> 1 dòng: câu, hệ thống hiểu, kết quả. Chặng / kết thúc của một lộ trình có thể nằm sau
    câu lệnh kế tiếp (vd "dừng lại") -> ghép theo sự kiện 'route' gần nhất phía trước."""
    ev = run.get('events', [])
    rows = []
    for k, e in enumerate(ev):
        if e.get('event') != 'command':
            continue
        text = br.esc(e['text'])
        nxt = ev[k + 1:]
        until = next((n for n, x in enumerate(nxt) if x.get('event') == 'command'), len(nxt))
        seg = nxt[:until]
        fb = [x['text'] for x in seg if x.get('event') == 'feedback']
        route = next((x for x in seg if x.get('event') == 'route'), None)
        if e['intent'] == 'invalid':
            got = 'khu vực không tồn tại: {}'.format(', '.join(e.get('unknown') or []) or '–')
            res = 'từ chối, robot đứng yên'
        elif e['intent'] == 'navigate' and route:
            # chặng + kết thúc của lộ trình này: tới trước sự kiện 'route' kế tiếp
            rest = nxt[nxt.index(route) + 1:]
            stop = next((n for n, x in enumerate(rest) if x.get('event') == 'route'), len(rest))
            mine = [x for x in rest[:stop] if x.get('mission') == route.get('mission')]
            legs = [x for x in mine if x.get('event') == 'leg']
            mission = next((x for x in mine if x.get('event') == 'mission'), None)
            got = '{} → {}; robot ở {}'.format('từ ' + e['start'] if e.get('start') else 'đi',
                                               ' → '.join(e['targets']), route.get('here') or '?')
            parts = []
            for x in legs:
                if x['status'] == 'SUCCEEDED':
                    parts.append('{}: tới sau {:.0f} s, sai số {:.2f} m'.format(
                        x['zone'], x['duration'], x.get('error_xy') or 0.0))
                else:
                    parts.append('{}: {}'.format(x['zone'], x['status']))
            if mission and mission.get('status') == 'CANCELED':
                parts.append('huỷ giữa đường theo lệnh dừng')
            elif mission and mission.get('status') == 'PREEMPTED':
                parts.append('thay bằng lệnh mới')
            elif mission is None:
                parts.append('(chưa kết thúc khi lưu)')
            res = 'lộ trình {} – '.format(' → '.join(route['legs'])) + '; '.join(parts)
        else:
            got = {'stop': 'dừng', 'where': 'hỏi vị trí', 'list': 'liệt kê khu vực'}.get(e['intent'], e['intent'])
            res = br.esc(fb[-1]) if fb else '–'
        rows.append([text, got, res])
    return rows


def content(info):
    names, zones = zone_names()
    run, run_note = load_run(info)
    S = [Paragraph(TITLE, title_st),
         Paragraph('{} · Video: {} · GitHub: {}'.format(
             br.esc(str(info.get('ho_ten') or '')), link(info.get('link_video')), link(info.get('link_github'))),
             sub_st)]
    S += [h('1. Hệ thống'),
          p('TurtleBot 4 (Gazebo Fortress, ROS 2 Humble) dùng bản đồ occupancy grid 20 m × 20 m tạo bằng SLAM ở Bài 4. '
            'Bản đồ được phân thành các khu vực có tên; người dùng nói câu lệnh tiếng Việt, hệ thống chuyển thành văn '
            'bản, tìm khu vực và gửi mục tiêu ' + M('NavigateToPose') + ' cho Nav2 (AMCL + NavFn + DWB, tránh vật '
            'cản bằng LiDAR). Toàn bộ chạy bằng một lệnh ' + M('ros2 launch tb4_lab04 voice_nav.launch.py') + '.')]
    S += br.figure(os.path.join(FIG, 'fig7_pipeline.png'), 'Hình 1 – Các node và luồng dữ liệu.', width_cm=13.0)
    S += [h('2. Phân vùng bản đồ và gắn nhãn'),
          p('<b>Tiền xử lý:</b> lấy ô trống đã biết, morphology opening 3×3 bỏ nhiễu, chỉ giữ phần robot (bán kính '
            '0,175 m) tới được từ dock. <b>Distance transform</b> (OpenCV) cho mỗi ô khoảng cách tới vật cản: tâm phòng '
            'là đỉnh, cửa là "yên ngựa". <b>Watershed theo độ bền:</b> duyệt ô theo khoảng cách giảm dần; hai lưu vực '
            'đỉnh p₁ ≥ p₂ gặp nhau ở mức s được <i>gộp</i> nếu s/p₂ &gt; 0,7 hoặc p₂ − s &lt; 0,3 m (chỗ gặp không hẹp '
            'hơn hẳn phòng – hành lang gồ ghề), ngược lại ranh giới chính là cửa. Vùng &lt; 5 m² gộp vào vùng kề có '
            'ranh giới dài nhất. <b>Điểm đích</b> mỗi vùng: ô tới được, không trùng vật thể, cách vật cản ≥ 0,5 m '
            '(&gt; inflation 0,45 m của Nav2), gần tâm vùng nhất. ID A, B, C… theo thứ tự đọc; tên có nghĩa gán bằng '
            'điểm neo trong ' + M('config/zone_names.yaml') + '. Kết quả: <b>{} khu vực</b>, tất cả hợp lệ, lưu ở '
            .format(len(zones)) + M('maps/zones.yaml') + ' (ID, tên, tâm, đích, diện tích, đa giác, vùng kề) và '
            + M('maps/zones_labels.pgm') + ' (ảnh nhãn để biết robot đang ở khu vực nào). Có thêm chế độ vẽ tay '
            '(đa giác) làm phương án dự phòng.')]
    S += br.figure(os.path.join(FIG, 'fig7_segmentation.png'),
                   'Hình 2 – (a) distance transform; (b) 12 khu vực: A Phòng học, B Hành lang, F Sảnh chính (dock), '
                   'H Phòng hội nghị, I Phòng thí nghiệm, K Thư viện; còn lại "Khu vực C/D/E/G/J/L".', width_cm=13.0)
    S += [h('3. Nhận dạng giọng nói và phân tích câu lệnh'),
          p('<b>ASR:</b> ' + M('speech_recognizer_node') + ' dùng Vosk (offline, model tiếng Việt '
            'vosk-model-small-vn-0.4, 32 MB, streaming, tự phát hiện hết câu) hoặc Whisper (faster-whisper int8, cắt câu '
            'bằng VAD năng lượng tự hiệu chỉnh); nguồn âm thanh là micro hoặc file WAV; kết quả lên ' + M('/voice/text')
            + '. Kiểm thử với Whisper thật cho thấy khi khó nghe, model chép lại initial prompt (prompt có câu mẫu "Đi '
            'đến khu vực A" làm "khu vực Z" thành "khu vực A", độ tin cậy lại cao nhất) hoặc lặp từ; vì vậy prompt chỉ '
            'chứa tên khu vực, và kết quả trùng prompt / lặp từ / lặp cụm bị bỏ ("không nghe rõ, nói lại"). Tên khu vực '
            'phải khác nhau rõ về âm: "phòng họp" bị nghe thành "phòng học" nên đổi thành "phòng hội nghị". '
            '<b>Phân tích:</b> chuẩn hoá chữ, tìm tên khu vực bằng khớp dài '
            'nhất trên chuỗi <i>không dấu</i> (chịu được ASR sai dấu, cách đọc chữ cái "bê, xê, đê"), gán vai trò theo '
            'từ khoá có dấu: "từ" = xuất phát, "đến/tới/về/rồi" = đích, "qua/ghé" = trung gian. Tên dài nói sai nhẹ '
            '("phòng thí nhiệm") được khớp gần đúng (≥ 0,84); ID chữ cái thì không, nên "khu vực Z" không bị đoán thành '
            '"khu vực C". Câu có khu vực không tồn tại bị từ chối cả câu, robot giữ nguyên và đọc danh sách khu vực.'),
          p('<b>Điều hướng:</b> ' + M('voice_navigator') + ' tra khu vực hiện tại từ TF map→base_link; "từ A đến B" '
            'khi robot không ở A thì lộ trình là [A, B]. Robot trong dock được undock trước; từng chặng gửi bằng '
            + M('NavigateToPose') + ', lỗi thì thử lại 1 lần; lệnh mới huỷ lộ trình cũ; "dừng lại" huỷ goal. Mở rộng: '
            'nhiều điểm đến trong một câu, RViz hiển thị khu vực (' + M('/voice/zones') + ') và đường dự kiến cả lộ '
            'trình tính trước bằng ' + M('ComputePathToPose') + ' (' + M('/voice/planned_route') + ').')]
    S += [h('4. Kết quả thử nghiệm')]
    rows = result_rows(run, names)
    S += br.table(['Câu lệnh (văn bản ASR)', 'Hệ thống hiểu', 'Kết quả'], rows, [4.4, 4.6, 7.0],
                  'Bảng 1 – Các câu lệnh trong một phiên chạy Gazebo + Nav2' + run_note + '.')
    run_png, run_note2 = pick('voice_run.png', os.path.join(FIG, 'test7_voice_run.png'))
    obs = ''
    if not os.path.isfile(os.path.join(USER, 'voice_run.png')):
        obs = '; lần chạy có vật cản (ô đen, không có trên bản đồ) đặt lên đường Nav2 lập ban đầu – robot vòng tránh'
    elif run.get('obstacles'):
        obs = '; ô đen = vật cản không có trên bản đồ, robot vòng tránh'
    S += br.figure(run_png, 'Hình 3 – Quỹ đạo robot trên bản đồ phân vùng{}{}.'.format(obs, run_note2), width_cm=7.6)
    extra = (info.get('nhan_xet_bai7') or '').strip()
    S += [p('<b>Unit test:</b> 46 test mới (203 tổng) – phân vùng bản đồ tổng hợp 2 phòng + cửa ra đúng 2 vùng, mọi '
            'điểm đích của bản đồ thật trống, cách tường ≥ 0,5 m và tới được; 3 câu ví dụ của đề, nhiều điểm đến, '
            'khu vực không tồn tại, VAD, và node ' + M('voice_navigator') + ' với rclpy thật. Kiểm thử tích hợp phát '
            'hiện và đã sửa thêm 3 lỗi: câu WAV đầu bị mất (publish trước khi DDS kết nối), node dừng hẳn khi gặp '
            'khu vực không tồn tại (rclpy cấm một dòng log đổi mức), robot kẹt trên mép dock khi bị dừng giữa lúc undock. <b>Đo ASR</b> (' + M('asr_benchmark.py') + ', 10 câu): Whisper base '
            'trên giọng máy espeak-ng đúng 5/10, không nghe rõ 2, đứng yên 3, <b>đi nhầm 0</b> – mức sàn, giọng người với '
            'model small cần tự đo. <b>Hạn chế:</b> phân vùng theo hình học nên tên chức năng do người đặt; mỗi khu vực '
            'chỉ một điểm đích cố định.' + (' ' + br.esc(extra) if extra else ''))]
    return S


def main():
    info = br.load_info()
    doc = br.Doc(OUT, pagesize=A4, leftMargin=2.0 * cm, rightMargin=2.0 * cm, topMargin=1.5 * cm,
                 bottomMargin=1.8 * cm, title=TITLE, author=str(info.get('ho_ten') or ''))
    doc.multiBuild(content(info))
    from pypdf import PdfReader
    n = len(PdfReader(OUT).pages)
    print('Đã tạo:', OUT, '({} trang)'.format(n))
    if n > 2:
        print('CẢNH BÁO: báo cáo dài hơn 2 trang – rút gọn nhan_xet_bai7 hoặc bảng kết quả.')
    miss = sorted(set(br.MISSING))
    if miss:
        print('CÒN THIẾU:', ', '.join(miss))
    if WARN:
        print('CẢNH BÁO: đang dùng dữ liệu KIỂM THỬ (môi trường ảo) cho: {} – thay bằng kết quả của bạn trước khi '
              'nộp.'.format(', '.join(sorted(set(WARN)))))


if __name__ == '__main__':
    main()
