#!/usr/bin/env python
from glob import glob
from distutils.core import setup

setup(name="PyOptionTree",
      version="0.21",
      description="Python OptionTree Configuration File Descriptor",
      author="Hoyt Koepke",
      author_email="hoytak@cs.ubc.ca",
      url="http://pyoptiontree.sourceforge.net",
      py_modules = [s[:-3] for s in  glob('PyOptionTree/*.py')],
      data_files=[('doc', glob('doc/*.html'))]
      )
      


