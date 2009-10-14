#!/usr/bin/env python
from distutils.core import setup
from usecase import version
from glob import glob

mod_files = [ f[:-3] for f in glob("*.py") ]
mod_files.remove("setup")

setup(name='PyUseCase',
      version=version,
      packages=["gtklogger"],
      py_modules=mod_files,
      scripts=["../bin/pyusecase"]
      )
