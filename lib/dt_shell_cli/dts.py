import os
import sys


def main():
    DTSHELL_LIB = os.environ.get("DTSHELL_LIB", None)

    if DTSHELL_LIB:
        DTSHELL_LIB = os.path.abspath(DTSHELL_LIB)
        # make sure the duckietown_shell library exists in the given path
        dt_shell_dir = os.path.join(DTSHELL_LIB, "dt_shell")
        if not os.path.exists(dt_shell_dir) or not os.path.isdir(dt_shell_dir):
            sys.stderr.write("FATAL: Duckietown Shell library not found in the given DTSHELL_LIB path. "
                             f"Directory '{dt_shell_dir}' does not exist.\n")
            sys.exit(1)
        # make sure the duckietown_shell library is a Python package
        dt_shell_init = os.path.join(DTSHELL_LIB, "dt_shell", "__init__.py")
        if not os.path.exists(dt_shell_init) or not os.path.isfile(dt_shell_init):
            sys.stderr.write(f"FATAL: The given directory '{dt_shell_dir}' is not a Python package.\n")
            sys.exit(2)
        # append given path to the system path
        sys.path.insert(0, DTSHELL_LIB)
        print(f"INFO: Using duckietown-shell library from '{DTSHELL_LIB}' as instructed by the environment "
              f"variable DTSHELL_LIB.")

    from dt_shell import cli_main
    # shell entrypoint
    cli_main()
