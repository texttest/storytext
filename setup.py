#!/usr/bin/env python
from distutils.core import setup
import sys
sys.path.insert(0, "lib")
from usecase import __version__
import os

def make_windows_script(src):
    outFile = open(src + ".py", "w")
    outFile.write("#!python.exe\nimport site\n\n")
    outFile.write(open(src).read())

mod_files = [ "ordereddict" ]
if sys.version_info[:2] < (2, 6):
    mod_files.append("ConfigParser26")
    
if os.name == "nt":
    make_windows_script("bin/pyusecase")
    make_windows_script("bin/usecase_name_chooser")
    scripts=["bin/pyusecase.py", "bin/pyusecase.exe", "bin/usecase_name_chooser.py", "bin/usecase_name_chooser.exe"]
else:
    scripts=["bin/pyusecase","bin/usecase_name_chooser"]


setup(name='PyUseCase',
      version=__version__,
      author="Geoff Bache",
      author_email="geoff.bache@pobox.com",
      url="http://www.texttest.org/index.php?page=ui_testing",
      description="An unconvential GUI-testing tool for UIs written with PyGTK or Tkinter",
      long_description='PyUseCase is an unconventional GUI testing tool for PyGTK and Tkinter. Instead of recording GUI mechanics directly, it asks the user for descriptive names and hence builds up a "domain language" along with a "UI map file" that translates it into the current GUI layout. The point is to reduce coupling, allow very expressive tests, and ensure that GUI changes mean changing the UI map file but not all the tests. Instead of an "assertion" mechanism, it auto-generates a log of the GUI appearance and changes to it. The point is then to use that as a baseline for text-based testing, using e.g. TextTest. It also includes support for instrumenting code so that "waits" can be recorded, making it far easier for a tester to record correctly synchronized tests without having to explicitly plan for this.',
      packages=["usecase", "usecase.gtktoolkit", "usecase.gtktoolkit.simulator", "usecase.gtktoolkit.describer", "usecase.javaswttoolkit"],
      package_dir={ "" : "lib"},
      py_modules=mod_files,
      classifiers=[ "Programming Language :: Python",
                    "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
                    "Operating System :: OS Independent",
                    "Development Status :: 5 - Production/Stable",
                    "Environment :: X11 Applications :: GTK",
                    "Environment :: Win32 (MS Windows)",
                    "Environment :: Console",
                    "Intended Audience :: Developers",
                    "Intended Audience :: Information Technology",
                    "Topic :: Software Development :: Testing",
                    "Topic :: Software Development :: Libraries :: Python Modules" ],
      scripts=scripts
      )
