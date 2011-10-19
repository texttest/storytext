

from usecase.javarcptoolkit import simulator as rcpsimulator

# Force classloading in the test thread where it works...
from org.eclipse.draw2d import *

class WidgetMonitor(rcpsimulator.WidgetMonitor):
    pass
