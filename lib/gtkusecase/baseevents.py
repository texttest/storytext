
""" The base classes from which widget record/replay classes are derived"""

from guiusecase import GuiEvent, MethodIntercept
from usecase import UseCaseScriptError
import gtk

# Abstract Base class for all GTK events
class GtkEvent(GuiEvent):
    def __init__(self, name, widget, *args):
        GuiEvent.__init__(self, name, widget)
        self.interceptMethod(self.widget.stop_emission, EmissionStopIntercept)
        self.interceptMethod(self.widget.emit_stop_by_name, EmissionStopIntercept)
        self.stopEmissionMethod = None
        
    @classmethod
    def getAssociatedSignal(cls, widget):
        return cls.signalName

    def getRecordSignal(self):
        return self.signalName

    def getUiMapSignature(self):
        return self.getRecordSignal()

    def connectRecord(self, method):
        self._connectRecord(self.widget, method)

    def _connectRecord(self, gobj, method):
        handler = gobj.connect(self.getRecordSignal(), method, self)
        gobj.connect(self.getRecordSignal(), self.stopEmissions)
        return handler

    def outputForScript(self, widget, *args):
        return self._outputForScript(*args)

    def stopEmissions(self, *args):
        if self.stopEmissionMethod:
            self.stopEmissionMethod(self.getRecordSignal())
            self.stopEmissionMethod = None

    def shouldRecord(self, *args):
        return GuiEvent.shouldRecord(self, *args) and self.widget.get_property("visible")

    def _outputForScript(self, *args):
        return self.name

    def checkWidgetStatus(self):
        if not self.widget.get_property("visible"):
            raise UseCaseScriptError, "widget '" + self.widget.get_name() + \
                  "' is not visible at the moment, cannot simulate event " + repr(self.name)

        if not self.widget.get_property("sensitive"):
            raise UseCaseScriptError, "widget '" + self.widget.get_name() + \
                  "' is not sensitive to input at the moment, cannot simulate event " + repr(self.name)

    def generate(self, argumentString):
        self.checkWidgetStatus()
        args = self.getGenerationArguments(argumentString)
        self.changeMethod(*args)


class EmissionStopIntercept(MethodIntercept):
    def __call__(self, sigName):
        stdSigName = sigName.replace("_", "-")
        for event in self.events:
            if stdSigName == event.getRecordSignal():
                event.stopEmissionMethod = self.method

        
# Generic class for all GTK events due to widget signals. Many won't be able to use this, however
class SignalEvent(GtkEvent):
    def __init__(self, name, widget, signalName=None):
        GtkEvent.__init__(self, name, widget)
        if signalName:
            self.signalName = signalName
        # else we assume it's defined at the class level
    @classmethod
    def getAssociatedSignal(cls, widget):
        if hasattr(cls, "signalName"):
            return cls.signalName
        elif isinstance(widget, gtk.Button) or isinstance(widget, gtk.ToolButton):
            return "clicked"
        elif isinstance(widget, gtk.Entry):
            return "activate"
    def getRecordSignal(self):
        return self.signalName
    def getChangeMethod(self):
        return self.widget.emit
    def getGenerationArguments(self, argumentString):
        return [ self.signalName ] + self.getEmissionArgs(argumentString)
    def getEmissionArgs(self, argumentString):
        return []


# Some widgets have state. We note every change but allow consecutive changes to
# overwrite each other. 
class StateChangeEvent(GtkEvent):
    signalName = "changed"
    def isStateChange(self):
        return True
    def shouldRecord(self, *args):
        return GtkEvent.shouldRecord(self, *args) and self.eventIsRelevant()
    def eventIsRelevant(self):
        return True
    def getGenerationArguments(self, argumentString):
        return [ self.getStateChangeArgument(argumentString) ]
    def getStateChangeArgument(self, argumentString):
        return argumentString
    def _outputForScript(self, *args):
        return self.name + " " + self.getStateDescription(*args)
        

class ClickEvent(SignalEvent):
    def shouldRecord(self, widget, event, *args):
        return SignalEvent.shouldRecord(self, widget, event, *args) and event.button == self.buttonNumber

    def getEmissionArgs(self, argumentString):
        area = self.getAreaToClick(argumentString)
        event = gtk.gdk.Event(self.eventType)
        event.x = float(area.x) + float(area.width) / 2
        event.y = float(area.y) + float(area.height) / 2
        event.button = self.buttonNumber
        return [ event ]

    def getAreaToClick(self, *args):
        return self.widget.get_allocation()


class LeftClickEvent(ClickEvent):
    signalName = "button-release-event" # Usually when left-clicking things (like buttons) what matters is releasing
    buttonNumber = 1
    eventType = gtk.gdk.BUTTON_RELEASE

class RightClickEvent(ClickEvent):
    signalName = "button-press-event"
    buttonNumber = 3
    eventType = gtk.gdk.BUTTON_PRESS
