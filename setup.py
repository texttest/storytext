#!/usr/bin/env python
from distutils.core import setup
from distutils.command.install_scripts import install_scripts
import sys
sys.path.insert(0, "lib")
from usecase import __version__
import os


mod_files = [ "ordereddict" ]
if sys.version_info[:2] < (2, 6):
    mod_files.append("ConfigParser26")

scripts = ["bin/pyusecase"]
if os.name == "java":
    # Revolting way to check if we're on Windows! Neither os.name nor sys.platform help when using Jython
    windows = os.pathsep == ";"
else:
    # Does not run under Jython, uses GTK
    scripts.append("bin/usecase_name_chooser")
    windows = os.name == "nt"


if windows:     
    command_classes = {'install_scripts': windows_install_scripts}
else:
    command_classes = {}

# Lifted from bzr setup.py
class windows_install_scripts(install_scripts):
    """ Customized install_scripts distutils action.
    Create pyusecase.bat for win32.
    """
    def run(self):
        install_scripts.run(self)   # standard action
        for script in scripts:
            localName = os.path.basename(script)
            try:
                scripts_dir = os.path.join(sys.prefix, 'Scripts')
                script_path = self._quoted_path(os.path.join(scripts_dir, localName))
                python_exe = self._quoted_path(sys.executable)
                args = '%*'
                batch_str = "@%s %s %s" % (python_exe, script_path, args)
                batch_path = os.path.join(self.install_dir, localName + ".bat")
                f = file(batch_path, "w")
                f.write(batch_str)
                f.close()
                print "Created:", batch_path
            except Exception, e:
                print "ERROR: Unable to create %s: %s" % (batch_path, e)

    def _quoted_path(self, path):
        if ' ' in path:
            return '"' + path + '"'
        else:
            return path

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
      scripts=scripts,
      cmdclass=command_classes
      )
