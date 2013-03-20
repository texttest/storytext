
""" Basic entry point, containing all methods and info likely to be required from an application.
    applicationEvent methods are for automating test synchronisation, shortcut method allows for
    hierarchical organisation of tests. See README file and online docs for more details."""

# Used by the command-line interface to store the instance it creates
scriptEngine = None
from .definitions import __version__

def applicationEvent(*args, **kwargs):
    if scriptEngine:
        scriptEngine.applicationEvent(*args, **kwargs)

def applicationEventRename(*args, **kwargs):
    if scriptEngine:
        scriptEngine.applicationEventRename(*args, **kwargs)

def applicationEventDelay(*args, **kwargs):
    if scriptEngine:
        scriptEngine.applicationEventDelay(*args, **kwargs)
        
def createShortcutBar(uiMapFiles=[], customEventTypes=[]):
    global scriptEngine
    if not scriptEngine: # pragma: no cover - cannot test with replayer disabled
        # Only available for GTK currently
        from . import gtktoolkit
        scriptEngine = gtktoolkit.ScriptEngine(universalLogging=False,
                                               uiMapFiles=uiMapFiles,
                                               customEventTypes=customEventTypes)
    elif uiMapFiles:
        scriptEngine.addUiMapFiles(uiMapFiles)
        scriptEngine.addCustomEventTypes(customEventTypes)
    return scriptEngine.createShortcutBar()
