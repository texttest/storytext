
""" Events for gtk.Windows of various types, including dialogs """

from baseevents import SignalEvent
import gtk, types

class DeletionEvent(SignalEvent):
    signalName = "delete-event"
    def getEmissionArgs(self, argumentString):
        return [ gtk.gdk.Event(gtk.gdk.DELETE) ]
            
    def generate(self, argumentString):
        SignalEvent.generate(self, argumentString)
        self.widget.destroy() # just in case...

    def shouldRecord(self, *args):
        return True # Even if the window is hidden, we still want to record it being closed...


class ResponseEvent(SignalEvent):
    signalName = "response"
    dialogInfo = {}
    def __init__(self, name, widget, responseId):
        SignalEvent.__init__(self, name, widget)
        self.responseId = self.parseId(responseId)
            
    def shouldRecord(self, widget, responseId, *args):
        return self.responseId == responseId and \
               SignalEvent.shouldRecord(self, widget, responseId, *args)

    @classmethod
    def getAssociatedSignatures(cls, widget):
        # RESPONSE_NONE is meant to be like None and shouldn't be recorded (at least not like this)
        names = filter(lambda x: x.startswith("RESPONSE_") and x != "RESPONSE_NONE", dir(gtk))
        return set((name.lower().replace("_", ".", 1) for name in names))

    @classmethod
    def storeApplicationConnect(cls, dialog, signalName, *args):
        cls.dialogInfo.setdefault(dialog, []).append((signalName, args))

    def getProgrammaticChangeMethods(self):
        return [ self.widget.response ]

    def _connectRecord(self, dialog, method):
        handler = dialog.connect_for_real(self.getRecordSignal(), method, self)
        dialog.connect_for_real(self.getRecordSignal(), self.stopEmissions)
        return handler

    @classmethod
    def connectStored(cls, dialog):
        # Finally, add in all the application's handlers
        for signalName, args in cls.dialogInfo.get(dialog, []):
            dialog.connect_for_real(signalName, *args)

    def getEmissionArgs(self, argumentString):
        return [ self.responseId ]

    def parseId(self, responseId):
        # May have to reverse the procedure in getResponseIdSignature
        if type(responseId) == types.StringType:
            return eval("gtk.RESPONSE_" + responseId.upper())
        else:
            return responseId

