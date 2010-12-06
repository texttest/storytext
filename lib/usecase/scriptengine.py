
""" Basic engine class, inherited in guishared.py and implemented by each GUI toolkit code """

import recorder, replayer, os, sys, imp

try:
    # In Py 2.x, the builtins were in __builtin__
    BUILTINS = sys.modules['__builtin__']
except KeyError: # pragma: no cover - not worried about Python 3 yet...
    # In Py 3.x, they're in builtins
    BUILTINS = sys.modules['builtins']


# Behaves as a singleton...
class ScriptEngine:
    usecaseHome = os.path.abspath(os.getenv("USECASE_HOME", os.path.expanduser("~/usecases")))
    def __init__(self, enableShortcuts=False, **kwargs):
        os.environ["USECASE_HOME"] = self.usecaseHome
        self.enableShortcuts = enableShortcuts
        self.recorder = recorder.UseCaseRecorder()
        self.replayer = self.createReplayer(**kwargs)

    def recorderActive(self):
        return self.enableShortcuts or self.recorder.isActive()

    def replayerActive(self):
        return self.enableShortcuts or self.replayer.isActive()

    def active(self):
        return self.replayerActive() or self.recorderActive()

    def createReplayer(self, **kwargs):
        return replayer.UseCaseReplayer()

    def applicationEvent(self, name, category=None, supercedeCategories=[], timeDelay=0.001):
        # Small time delay to avoid race conditions: see replayer
        if self.recorderActive():
            self.recorder.registerApplicationEvent(name, category, supercedeCategories)
        if self.replayerActive():
            self.replayer.registerApplicationEvent(name, timeDelay)
            
    def applicationEventRename(self, oldName, newName, oldCategory=None, newCategory=None):
        # May need to recategorise in the recorder
        if self.recorderActive() and oldCategory != newCategory:
            self.recorder.applicationEventRename(oldName, newName, oldCategory, newCategory)
        if self.replayerActive():
            self.replayer.applicationEventRename(oldName, newName)

    def run(self, options, args):
        if len(args) == 0:
            return False
        else:
            self.run_python_file(args)
            if self.recorderActive():
                self.recorder.terminate()
            return True

    def run_python_file(self, args):
        """Run a python file as if it were the main program on the command line.

        `args` is the argument array to present as sys.argv, including the first
        element representing the file being executed.

        Lifted straight from coverage.py by Ned Batchelder

        """
        filename = args[0]
        # Create a module to serve as __main__
        old_main_mod = sys.modules['__main__']
        main_mod = imp.new_module('__main__')
        sys.modules['__main__'] = main_mod
        main_mod.__file__ = filename
        main_mod.__builtins__ = BUILTINS

        # Set sys.argv and the first path element properly.
        old_argv = sys.argv
        old_path0 = sys.path[0]
        sys.argv = args
        sys.path[0] = os.path.dirname(filename)

        try:
            source = open(filename, 'rU').read()
            exec compile(source, filename, "exec") in main_mod.__dict__
        finally:
            # Restore the old __main__
            sys.modules['__main__'] = old_main_mod

            # Restore the old argv and path
            sys.argv = old_argv
            sys.path[0] = old_path0

        
