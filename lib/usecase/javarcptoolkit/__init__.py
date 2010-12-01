
""" Don't load any Java stuff at global scope, needs to be importable by CPython also """

import usecase.guishared

class ScriptEngine(usecase.guishared.ScriptEngine):
    eventTypes = [] # Can't set them up until the Eclipse class loader is available
    signalDescs = {}
    def createReplayer(self, universalLogging=False):
        from replayer import UseCaseReplayer
        return UseCaseReplayer(self.uiMap, universalLogging, self.recorder)

    def run_python_file(self, args):
        import org.eclipse.equinox.launcher as launcher
        cmdArgs = [ "-application", "org.eclipse.swtbot.testscript.application",
                    "-testApplication" ] + args
        launcher.Main.main(cmdArgs)

    def _createSignalEvent(self, eventName, eventDescriptor, widget, argumentParseData):
        for eventClass in self.findEventClassesFor(widget):
            if eventDescriptor in eventClass.getAssociatedSignatures(widget):
                return eventClass(eventName, widget, argumentParseData)
