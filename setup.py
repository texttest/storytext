#!/usr/bin/env python
from distutils.core import setup
from usecase import version

setup(name='PyUseCase',
      version=version,
      py_modules=["usecase", "gtkusecase", "gtktreeviewextract", 
                  "gtklogger", "gtkloggertreeview", "gtkloggerimage", "ndict", "jobprocess"],
      scripts=["pyusecase"]
      )
