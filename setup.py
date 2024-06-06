import os
import sys

from setuptools import setup, find_packages


def get_version(filename):
    import ast
    version = None
    with open(filename) as f:
        for line in f:
            if line.startswith('__version__'):
                version = ast.parse(line).body[0].value.s
                break
        else:
            raise ValueError('No version found in %r.' % filename)
    if version is None:
        raise ValueError(filename)
    return version


if sys.version_info < (3, 6):
    msg = 'duckietown-shell works with Python 3.6 and later.\nDetected %s.' % str(sys.version)
    sys.exit(msg)

distro = 'daffy'

shell_version = get_version(filename='lib/dt_shell/__init__.py')

shell_requires = [
    "termcolor>=2.3.0,<3",
    "requests>=2.31.0,<3",
    # force pyyaml away from specific versions: https://github.com/yaml/pyyaml/issues/724
    "pyyaml!=6.0.0,!=5.4.0,!=5.4.1,<7",

    # CLI utils
    "pyfiglet>=0.8.0,<1",
    "questionary>=2.0.1,<3",
    "argcomplete>=3.1.4,<4",

    # database concurrent access control
    "filelock>=3,<4",

    # duckietown deps
    "dockertown>=0.2.5,<1",
    "dtproject>=1.0.6,<2",
    "dt-authentication>=2.1.4,<3",
    # TODO: this cannot be released until DCSS is released on the HUB
    'dt-data-api>=2.0.0,<3',
]

compatibility_requires = [
    # NOTE: this is used by checks/environment.py and cannot be removed for compatibility
    "docker>=6.1.3,<7",
]

install_requires = shell_requires + compatibility_requires

system_version = tuple(sys.version_info)[:3]
if system_version < (3, 7):
    install_requires.append('dataclasses')


# embed requirements as asset into the release
requirements_fpath: str = os.path.join(
    os.path.dirname(__file__), "lib", "dt_shell", "assets", "requirements.txt"
)
with open(requirements_fpath, "wt") as fout:
    fout.write("\n".join(shell_requires))


setup(
    name='duckietown-shell',
    version=shell_version,
    download_url='http://github.com/duckietown/duckietown-shell/tarball/%s' % shell_version,
    package_dir={
        'dt_shell': 'lib/dt_shell',
        'dt_shell_cli': 'lib/dt_shell_cli',
    },
    packages=find_packages("lib", exclude=["dt_shell_tests"]),
    # we want the python 2 version to download it, and then exit with an error
    # python_requires='>=3.6',

    tests_require=[],
    install_requires=install_requires,
    # This avoids creating the egg file, which is a zip file, which makes our data
    # inaccessible by dir_from_package_name()
    zip_safe=False,

    # without this, the stuff is included but not installed
    include_package_data=True,
    package_data={
        'dt_shell': [
            'embedded/*',
            'embedded/*/*',
            'embedded/*/*/*',
            'embedded/*/*/*/*',
            'assets/*',
            'assets/*/*',
            'assets/*/*/*',
            'assets/*/*/*/*',
        ],
        'dt_shell_cli': [],
    },

    entry_points={
        'console_scripts': [
            'dts = dt_shell_cli.dts:dts',
        ]
    }
)
