"""A setuptools based setup module.
See:
https://packaging.python.org/en/latest/distributing.html
https://github.com/pypa/sampleproject
"""


import re

# Always prefer setuptools over distutils
from setuptools import setup, find_packages
# To use a consistent encoding
from codecs import open
from os import path


here = path.abspath(path.dirname(__file__))

if path.isfile('README.md'):
    with open(path.join(here, 'README.md'), encoding='utf-8') as f:
        long_description = f.read()
else:
    long_description = ""

def read(*parts):
    # intentionally *not* adding an encoding option to open
    # see here: https://github.com/pypa/virtualenv/issues/201#issuecomment-3145690
    return open(path.join(here, *parts), 'r').read()

def find_version(*file_paths):
    version_file = read(*file_paths)
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")

setup(
    name='deployer',

    version=find_version('deployer', '__init__.py'),

    description='CloudFormation Deployer',
    long_description=long_description,
    long_description_content_type="text/markdown",

    # The project's main homepage.
    url='https://github.com/RightBrain-Networks/deployer',

    # Author details
    author='RightBrain Networks',
    author_email='cloud@rightbrainnetworks.com',

    # Choose your license
    license='Apache2.0',

    # See https://pypi.org/classifiers/
    classifiers=[
        'Development Status :: 4 - Beta',
        'Intended Audience :: Developers',
        'Intended Audience :: System Administrators',
        'Topic :: Software Development :: Build Tools',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
    ],
    keywords='Amazon,CloudFormation,Deploy,Deployment',
    packages=find_packages(exclude=['contrib', 'docs', 'tests']),
    install_requires=[
        'boto3>=1.9.0',
        'pyyaml>=3.12',
        'tabulate>=0.7.5',
        'pytz>=2017.2',
        'ruamel.yaml>=0.15.33',
        'parse>=1.8.2',
        'jinja2>=2.8',
        'GitPython>=2.1.11',
        'pip'
    ],
    package_data={
        '' : ['*.yaml'],
    },
    include_package_data = True,
    entry_points={
        'console_scripts': [
            'deployer = deployer:main',
            'config_updater = deployer.config_updater:main'
        ],
    },
)
