#!/usr/bin/env python

import logconfiggen, os
    
if __name__ == "__main__":
    gen = logconfiggen.PythonLoggingGenerator("logging.sample", postfix="sample")
    enabledLoggerNames = [ ("gui log", "gui_log"), ("storytext replay log", "gui_log") ]
    
    installationRoot = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    coreLib = os.path.join(installationRoot, "lib")
    coreLoggers = logconfiggen.findLoggerNamesUnder(coreLib)
        
    gen.generate(enabledLoggerNames, coreLoggers)
    
