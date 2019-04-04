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

      version=shell_version,
      download_url='http://github.com/duckietown/duckietown-shell/tarball/%s' % shell_version,
      package_dir={'': 'lib'},
      packages=find_packages('lib'),
      # we want the python 2 version to download it, and then exit with an error
      # python_requires='>=3.6',
      install_requires=[
          'GitPython',
          'texttable',
          'base58',
          'ecdsa',
          'python-dateutil',
          'whichcraft',
          'termcolor',
          'PyYAML',
          'docker',
          'six',
          'psutil',
          'future',
          'duckietown-challenges==4.0.6',
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
              'dts = dt_shell:cli_main',
          ]
      }
      )
