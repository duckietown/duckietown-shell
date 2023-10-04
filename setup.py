import os
import sys

from setuptools import setup

from setuptools.command.develop import develop
from setuptools.command.install import install


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
    "argparse",

    # TODO: check these and see if they are used
    "GitPython",
    "texttable",
    "python-dateutil",
    "termcolor",
    "PyYAML",
    "six",
    "psutil",
    "future",
    "pytz",

    # CLI utils
    "pyfiglet>=1.0.2,<2",
    "questionary>=2.0.1,<3",

    # duckietown deps
    "dockertown>=0.2.2,<1",
    "dtproject>=0.0.5,<1",
    "dt-authentication>=2.1.4,<3",
]

compatibility_requires = [
    # TODO: we should clear these by releasing non-distro version of them and moving them to the list above
    'dt-authentication-{}'.format(distro),
    'dt-data-api-{}>=1.2.0'.format(distro),
    'duckietown-docker-utils-{}>=6.0.90'.format(distro),
]

commands_require = [
    # TODO: these are used by the commands and should be removed
    "netifaces",
    "docker",
    "docker-compose",
    "dt-data-api>=1.2.0",
    "duckietown-docker-utils>=6.0.90",
]

# TODO: compatibility should be cleared out and removed before releasing v6
# TODO: commands should be cleared out and removed before releasing v6
install_requires = shell_requires + compatibility_requires + commands_require

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
    packages=[
        'dt_shell',
        'dt_shell.checks',
        'dt_shell.commands',
        'dt_shell.compatibility',
        'dt_shell.database',
        'dt_shell_cli'
    ],
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
        'dt_shell': ['embedded/*/*', 'assets/*'],
        'dt_shell_cli': [],
    },

    # additional data files
    # data_files=[
    #     ("dt_shell", ["dependencies.txt"]),
    # ],

    entry_points={
        'console_scripts': [
            'dts = dt_shell_cli.dts:dts',
        ]
    }
)
