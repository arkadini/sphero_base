#!/usr/bin/python

"""sphero_base
===========

A very crude Python3-compatible implementation of a subset of Sphero API.
"""

from distutils.core import setup


__version__ = '0.1.2'

setup(name='sphero-base',
      version=__version__,
      description='A very crude Python3-compatible subset of Sphero API',
      long_description=__doc__,
      platforms=['any'],
      license='MIT License',
      author='Arek Korbik',
      author_email='arkadini@gmail.com',
      maintainer='Arek Korbik',
      maintainer_email='arkadini@gmail.com',
      url='http://github.com/arkadini/sphero_base',
      packages=['sphero_base'])
