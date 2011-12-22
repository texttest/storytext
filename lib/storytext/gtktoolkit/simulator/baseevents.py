
""" The base classes from which widget record/replay classes are derived"""

from storytext.guishared import GuiEvent, MethodIntercept
from storytext.definitions import UseCaseScriptError
import gtk, gobject

# Abstract Base class for all GTK events
class GtkEvent(GuiEvent):
    def __init__(self, name, widget, *args):
        GuiEvent.__init__(self, name, widget)
        self.interceptMethod(self.widget.stop_emission, EmissionStopIntercept)
        self.interceptMethod(self.widget.emit_stop_by_name, EmissionStopIntercept)
        self.interceptMethod(self.widget.get_toplevel().destroy, DestroyIntercept)
        self.stopEmissionMethod = None
        self.destroyMethod = None

    @staticmethod
    def disableIntercepts(window):
        if isinstance(window.destroy, MethodIntercept):
            window.destroy = window.destroy.method

    @classmethod
    def getAssociatedSignal(cls, widget):
        return cls.signalName

    @classmethod
    def canHandleEvent(cls, widget, signalName, *args):
        return cls.getAssociatedSignal(widget) == signalName and cls.widgetHasSignal(widget, signalName)

    @staticmethod
    def widgetHasSignal(widget, signalName):
        if widget.isInstanceOf(gtk.TreeView):
            # Ignore this for treeviews: as they have no title/label they can't really get confused with other stuff
            return widget.get_model() is not None
        else:
            return gobject.signal_lookup(signalName, widget.widget) != 0
        
    def delayLevel(self, *args):
        # If we get this when in dialog.run, the event that cause us has not yet been
        # recorded, so we should delay
        topLevel = self.widget.get_toplevel()
        return int(hasattr(topLevel, "dialogRunLevel") and topLevel.dialogRunLevel > 0)

    def getRecordSignal(self):
        return self.signalName

    def connectRecord(self, method):
        self._connectRecord(self.widget, method)

    def _connectRecord(self, gobj, method):
        handler = gobj.connect(self.getRecordSignal(), method, self)
        gobj.connect(self.getRecordSignal(), self.executePostponedActions)
        return handler

    def outputForScript(self, widget, *args):
        return self._outputForScript(*args)

    def executePostponedActions(self, *args):
        if self.stopEmissionMethod:
            self.stopEmissionMethod(self.getRecordSignal())
            self.stopEmissionMethod = None
        if self.destroyMethod:
            self.destroyMethod()

    def shouldRecord(self, *args):
        return GuiEvent.shouldRecord(self, *args) and self.widget.get_property("visible")

    def _outputForScript(self, *args):
        return self.name

    def widgetVisible(self):
        return self.widget.get_property("visible")

    def widgetSensitive(self):
        return self.widget.get_property("sensitive")

    def describeWidget(self):
        return repr(self.widget.get_name())

    def generate(self, argumentString):
        self.checkWidgetStatus()
        args = self.getGenerationArguments(argumentString)
        try:
            self.changeMethod(*args)
        except TypeError:
            raise UseCaseScriptError, "Cannot generate signal " + repr(self.signalName) + \
                  " for  widget of type " + repr(self.widget.getType())


class EmissionStopIntercept(MethodIntercept):
    def __call__(self, sigName):
        stdSigName = sigName.replace("_", "-")
        for event in self.events:
            if stdSigName == event.getRecordSignal():
                event.stopEmissionMethod = self.method

class DestroyIntercept(MethodIntercept):
    inResponseHandler = False    
    def __call__(self):
        if self.inResponseHandler:
            self.method()
        else:
            for event in self.events:
                event.destroyMethod = self.method

        
# Generic class for all GTK events due to widget signals. Many won't be able to use this, however
class SignalEvent(GtkEvent):
    def __init__(self, name, widget, signalName=None):
        GtkEvent.__init__(self, name, widget)
        if signalName:
            self.signalName = signalName
        else:
            self.signalName = self.getAssociatedSignal(widget)

    @classmethod
    def getAssociatedSignal(cls, widget):
        if hasattr(cls, "signalName"):
            return cls.signalName
        elif widget.isInstanceOf(gtk.Button) or widget.isInstanceOf(gtk.ToolButton):
            return "clicked"
        elif widget.isInstanceOf(gtk.Entry):
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
