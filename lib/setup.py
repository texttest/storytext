#!/usr/bin/env python
from distutils.core import setup
from usecase import version
from glob import glob
import os

def make_windows_script(src):
    outFile = open(src + ".py", "w")
    outFile.write("#!python.exe\nimport site\n\n")
    outFile.write(open(src).read())

mod_files = [ f[:-3] for f in glob("*.py") ]
mod_files.remove("setup")
if os.name == "nt":
    make_windows_script("../bin/pyusecase")
    scripts=["../bin/pyusecase.py", "../bin/pyusecase.exe"]
else:
    scripts=["../bin/pyusecase"]


setup(name='PyUseCase',
      version=version,
      packages=["gtklogger","gtkusecase"],
      py_modules=mod_files,
      scripts=scripts
      )
