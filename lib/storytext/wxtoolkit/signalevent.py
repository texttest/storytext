import wx

import storytext.guishared
from storytext.definitions import UseCaseScriptError


class SignalEvent(storytext.guishared.GuiEvent):
    
    def connectRecord(self, method):
        self._connectRecord(method, self.widget)

    def _connectRecord(self, method, widget):
        def handler(event):
            method(event, self)
            event.Skip()
        widget.Bind(self.event, handler)

    def makeCommandEvent(self, eventType):
        try:
            widgetId = self.widget.widget.GetId()
        except:
            raise UseCaseScriptError, "Widget is no longer active"
        command = wx.CommandEvent(eventType, widgetId)
        command.SetEventObject(self.widget.widget)
        return command
        
    @classmethod
    def getAssociatedSignal(cls, widget):
        return cls.signal

    def generate(self, argumentString):
        pass
