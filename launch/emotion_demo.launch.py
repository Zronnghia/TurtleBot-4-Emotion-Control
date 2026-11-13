# Bài 8 – chạy tất cả trong một lệnh: Gazebo + TurtleBot 4 (sân trống gesture_arena) + nhận diện biểu cảm
# + điều khiển theo biểu cảm.
#
#   ros2 launch tb4_lab04 emotion_demo.launch.py
#   ros2 launch tb4_lab04 emotion_demo.launch.py camera_source:=1 backend:=fer software_render:=true
#
# Hai node biểu cảm được bật khi mô phỏng đã THỰC SỰ chạy (wait_for_sim.py thấy /clock + /odom).
# Tham số của emotion.launch.py (camera_source, backend, mode, ...) truyền thẳng ở dòng lệnh này.

import os
import sys

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, LogInfo
from launch.launch_description_sources import PythonLaunchDescriptionSource

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tb4_lab04_common as common  # noqa: E402


def generate_launch_description():
    abort = common.abort_if_missing(common.PKGS_SIM)
    if abort is not None:
        return abort
    pkg = get_package_share_directory(common.PKG)
    emotion = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(os.path.join(pkg, 'launch', 'emotion.launch.py')))
    wait = common.wait_for_sim_node()
    return LaunchDescription(
        common.sim_arguments('sim.rviz', world_note='World Gazebo (gesture_arena = sân trống 9 x 9 m)',
                             default_world='gesture_arena', default_rviz='false')
        + common.render_env()
        + [common.rviz_node(), common.turtlebot4_sim(), wait,
           common.after_sim_ready(wait, [LogInfo(msg='[tb4_lab04] Mô phỏng sẵn sàng -> bật node biểu cảm'),
                                         emotion])]
    )
