#!/usr/bin/env python
from distutils.core import setup
from usecase import version

setup(name='PyUseCase',
      version=version,
      py_modules=["usecase", "gtkusecase", "gtklogger", "gtkloggertreeview", "ndict", "jobprocess"],
      scripts=["pyusecase"]
      )
