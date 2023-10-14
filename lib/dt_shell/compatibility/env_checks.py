# used by the following commands files:
#
#   - start_gui_tools/command.py
#   - build_utils/command.py
#   - chalenges/command.py
#   - code/workbench/command.py
#   - duckiebot/calibrate_intrinsics/command.py
#   - duckiebot/demo/command.py
#   - duckiebot/evaluate/command.py
#   - duckiebot/keyboard_control/command.py
#   - duckiebot/led_control/command.py
#   - excercises/build/command.py
#   - exerrcises/test/command.py
#   - utils/docker_utils.py
#
def check_docker_environment():
    from dt_shell.checks.environment import check_docker_environment
    return check_docker_environment()


# used by the following commands files:
#
#   - build_utils/command.py
#   - chalenges/command.py
#
def check_package_version(*args, **kwargs):
    pass
