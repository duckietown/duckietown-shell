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


shell_version = get_version(filename='lib/dt_shell/__init__.py')

setup(name='duckietown-shell',
      # only for Python 2
      python_requires="<3.0",
      version=shell_version,
      download_url='http://github.com/duckietown/duckietown-shell/tarball/%s' % shell_version,
      package_dir={'': 'lib'},
      packages=find_packages('lib'),
      install_requires=[
          'GitPython',
          'texttable',
          'docker',
          'base58',
          'ecdsa',
          'python-dateutil',
          'SystemCmd',
          'PyContracts',  # XXX: should be a dep for SystemCmd
          'whichcraft',
          'termcolor',
          'PyYAML',
          'docker',
          'ruamel.yaml',
          'ruamel.ordereddict',
      ],

      tests_require=[
      ],

      # This avoids creating the egg file, which is a zip file, which makes our data
      # inaccessible by dir_from_package_name()
      zip_safe=False,

      # without this, the stuff is included but not installed
      include_package_data=True,

      entry_points={
          'console_scripts': [
              'dt = dt_shell:cli_main',
              'dts = dt_shell:cli_main',
          ]
      }
      )
