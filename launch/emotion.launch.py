# Bài 8: node nhận diện biểu cảm (webcam + DeepFace/FER) và node điều khiển TurtleBot 4 qua /cmd_vel.
#
#   ros2 launch tb4_lab04 emotion.launch.py                       # mô phỏng đã chạy ở terminal khác
#   ros2 launch tb4_lab04 emotion.launch.py camera_source:=1      # webcam USB
#   ros2 launch tb4_lab04 emotion.launch.py backend:=fer          # dùng FER thay DeepFace
#   ros2 launch tb4_lab04 emotion.launch.py mode:=repeat          # lặp quỹ đạo khi còn giữ biểu cảm
#   ros2 launch tb4_lab04 emotion.launch.py run_behavior:=false   # chỉ thử nhận diện (không có robot)
#
# Tham số đầy đủ: config/emotion.yaml. Tham số launch để trống = giữ giá trị trong file.

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

PKG = 'tb4_lab04'


def _bool(v):
    return v.strip().lower() in ('1', 'true', 'yes', 'on')


# tham số launch -> (node, tên tham số, hàm đổi kiểu)
OVERRIDES = {
    'camera_source': ('rec', 'camera_source', str),
    'show_window': ('rec', 'show_window', _bool),
    'mirror': ('rec', 'mirror', _bool),
    'window_position': ('rec', 'window_position', str),
    'backend': ('rec', 'backend', str),
    'mode': ('beh', 'mode', str),
    'stop_on_no_face': ('beh', 'stop_on_no_face', _bool),
    'auto_undock': ('beh', 'auto_undock', _bool),
    'setup_forward': ('beh', 'setup_forward', float),
}


def _setup(context, *args, **kwargs):
    params_file = LaunchConfiguration('emotion_params_file').perform(context)
    over = {'rec': {}, 'beh': {}}
    for arg, (who, name, conv) in OVERRIDES.items():
        val = LaunchConfiguration(arg).perform(context).strip()
        if val:
            over[who][name] = conv(val)
    nodes = []
    if _bool(LaunchConfiguration('run_recognition').perform(context)):
        nodes.append(Node(package=PKG, executable='emotion_recognition_node.py',
                          name='emotion_recognition_node', output='screen', emulate_tty=True,
                          parameters=[params_file, over['rec']]))
    if _bool(LaunchConfiguration('run_behavior').perform(context)):
        nodes.append(Node(package=PKG, executable='emotion_behavior_node.py',
                          name='emotion_behavior_node', output='screen', emulate_tty=True,
                          parameters=[params_file, over['beh']]))
    return nodes


def generate_launch_description():
    pkg = get_package_share_directory(PKG)
    return LaunchDescription([
        DeclareLaunchArgument('emotion_params_file',
                              default_value=os.path.join(pkg, 'config', 'emotion.yaml'),
                              description='File tham số của 2 node biểu cảm'),
        DeclareLaunchArgument('run_recognition', default_value='true', choices=['true', 'false'],
                              description='Chạy emotion_recognition_node (webcam + DeepFace/FER)'),
        DeclareLaunchArgument('run_behavior', default_value='true', choices=['true', 'false'],
                              description='Chạy emotion_behavior_node (/cmd_vel)'),
        DeclareLaunchArgument('camera_source', default_value='',
                              description='0 = webcam laptop, 1 = webcam USB, /dev/videoN, file video, thư mục ảnh'),
        DeclareLaunchArgument('show_window', default_value='', description='true/false – cửa sổ camera + kết quả'),
        DeclareLaunchArgument('mirror', default_value='', description='true/false – lật gương ảnh webcam'),
        DeclareLaunchArgument('window_position', default_value='',
                              description='"x,y" – vị trí cửa sổ webcam trên màn hình (vd 1000,0)'),
        DeclareLaunchArgument('backend', default_value='', description='deepface | fer | auto'),
        DeclareLaunchArgument('mode', default_value='',
                              description='once: mỗi lần đổi biểu cảm chạy 1 quỹ đạo | repeat: lặp khi còn giữ'),
        DeclareLaunchArgument('stop_on_no_face', default_value='',
                              description='true/false – không thấy mặt thì dừng robot'),
        DeclareLaunchArgument('auto_undock', default_value='',
                              description='true/false – tự rời dock + ra giữa sân khi khởi động'),
        DeclareLaunchArgument('setup_forward', default_value='',
                              description='m – quãng chạy thẳng ra giữa sân sau khi undock'),
        OpaqueFunction(function=_setup),
    ])
