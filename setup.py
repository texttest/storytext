#!/usr/bin/env python
from distutils.core import setup
import sys
sys.path.insert(0, "lib")
from usecase import version
from glob import glob
import os

def make_windows_script(src):
    outFile = open(src + ".py", "w")
    outFile.write("#!python.exe\nimport site\n\n")
    outFile.write(open(src).read())

mod_files = [ os.path.basename(f[:-3]) for f in glob("lib/*.py") ]
if os.name == "nt":
    make_windows_script("bin/pyusecase")
    make_windows_script("bin/usecase_name_chooser")
    scripts=["bin/pyusecase.py", "bin/pyusecase.exe", "bin/usecase_name_chooser.py", "bin/usecase_name_chooser.exe"]
else:
    scripts=["bin/pyusecase","bin/usecase_name_chooser"]


setup(name='PyUseCase',
      version=version,
      packages=["gtklogger","gtkusecase"],
      package_dir={ "" : "lib"},
      py_modules=mod_files,
      scripts=scripts
      )
