import sys

from setuptools import find_packages, setup


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
install_requires = [
    'GitPython',
    'texttable',
    'base58',
    'ecdsa',
    'python-dateutil',
    'whichcraft',
    'termcolor',
    'PyYAML',
    'docker',
    'docker-compose',
    'six',
    'psutil',
    'future',
    'duckietown-docker-utils-{}>=6.0.90'.format(distro),
    'zeroconf',
    'requests',
    'pytz',
    'dt-authentication-{}'.format(distro),
    'dt-data-api-{}>=0.1.6'.format(distro),
    "pip",
]

system_version = tuple(sys.version_info)[:3]
if system_version < (3, 7):
    install_requires.append('dataclasses')

setup(
    name='duckietown-shell',
    version=shell_version,
    download_url='http://github.com/duckietown/duckietown-shell/tarball/%s' % shell_version,
    package_dir={'': 'lib'},
    packages=['dt_shell'],
    # we want the python 2 version to download it, and then exit with an error
    # python_requires='>=3.6',

    tests_require=[],
    install_requires=install_requires,
    # This avoids creating the egg file, which is a zip file, which makes our data
    # inaccessible by dir_from_package_name()
    zip_safe=False,

    # without this, the stuff is included but not installed
    include_package_data=True,

    entry_points={
        'console_scripts': [
            'dts = dt_shell:cli_main',
        ]
    }
)
