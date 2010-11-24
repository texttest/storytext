
"""
The idea of this module is to implement a generic record/playback framework, independent of
particular GUI frameworks or anything. The only GUI toolkit support by PyUseCase right now is
PyGTK but in principle all the code in this module would be useful for PyQT or wxPython also.

It's also useful for console applications in recording and replaying signals sent to the process.

The module reads the following environment variables. These are set by TextTest, and also
from the pyusecase command line
USECASE_RECORD_SCRIPT (-r)
USECASE_REPLAY_SCRIPT (-p)
USECASE_REPLAY_DELAY  (-d)

The functionality present here is therefore
    
(1) Record and replay for signals received by the process
    - This just happens. If the process gets SIGINT, 'receive signal SIGINT' is recorded
    
(2) Recording specified 'application events'
    - These are events that are not caused by the user doing something, generally the
    application enters a certain state. 

    usecase.applicationEvent("idle handler exit")

    Recording will take the form of recording a "wait" command in USECASE_RECORD_SCRIPT in this
    case as "wait for idle handler exit". When such a command is read from USECASE_REPLAY_SCRIPT,
    the script will suspend and wait to be told that this application event has occurred before proceeding.

    By default, these will overwrite each other, so that only the last one before any other event
    is recorded in the script.

    To override this, you can provide an optional second argument as a 'category', meaning that
    only events in the same category will overwrite each other. Events with no category will
    overwrite all events in all categories.

(3) Basic framework for GUI testing
    - The aim is to handle the boilerplate around a recorder and a replayer here, while
    letting particular extensions fill out which widgets they support. One such extension is currently
    available for PyGTK (gtkusecase.py)
"""

# Used by the command-line interface to store the instance it creates
scriptEngine = None
from definitions import __version__

def applicationEvent(*args, **kwargs):
    if scriptEngine:
        scriptEngine.applicationEvent(*args, **kwargs)

def applicationEventRename(*args, **kwargs):
    if scriptEngine:
        scriptEngine.applicationEventRename(*args, **kwargs)

def createShortcutBar(uiMapFiles=[], customEventTypes=[]):
    global scriptEngine
    if not scriptEngine: # pragma: no cover - cannot test with replayer disabled
        # Only available for GTK currently
        import gtktoolkit
        scriptEngine = gtktoolkit.ScriptEngine(universalLogging=False,
                                               uiMapFiles=uiMapFiles,
                                               customEventTypes=customEventTypes)
    elif uiMapFiles:
        scriptEngine.addUiMapFiles(uiMapFiles)
        scriptEngine.addCustomEventTypes(customEventTypes)
    return scriptEngine.createShortcutBar()
