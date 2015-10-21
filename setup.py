#!/usr/bin/env python

from setuptools import setup, find_packages
from pip.req import parse_requirements

setup(
      name='me7'
   ,  version='0.0.1'
   ,  description='Interface to Bosch ME7 ECUs'
   ,  author='derpston'
   ,  author_email='derpston@example.com'
   ,  url='https://example.com'
   ,  install_requires=['pylibftdi']
   ,  test_suite='tests'
)
