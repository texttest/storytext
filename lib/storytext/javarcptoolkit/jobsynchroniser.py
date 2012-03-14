
""" Eclipse RCP has its own mechanism for background processing
    Hook application events directly into that for synchronisation."""

import logging
from storytext import applicationEvent
from storytext.javaswttoolkit.simulator import DisplayFilter
from org.eclipse.core.runtime.jobs import Job, JobChangeAdapter
from threading import Lock

class JobListener(JobChangeAdapter):
    # Add things from customwidgetevents here, if desired...
    systemJobNames = []
    def __init__(self):
        self.jobNameToUse = None
        self.jobCount = 0
        self.jobCountLock = Lock()
        self.afterOthers = False
        self.logger = logging.getLogger("Eclipse RCP jobs")
        
    def done(self, e):
        jobName = e.getJob().getName().lower()        
        self.alterJobCount(-1)
        self.logger.debug("Completed " + ("system" if e.getJob().isSystem() else "non-system") + " job '" + jobName + "' jobs = " + repr(self.jobCount))    
        # We wait for the system to reach a stable state, i.e. no scheduled jobs
        # Would be nice to call Job.getJobManager().isIdle(),
        # but that doesn't count scheduled jobs for some reason
        if self.jobCount == 0 and self.jobNameToUse: 
            self.setComplete()

    def setComplete(self):
        applicationEvent("completion of " + self.jobNameToUse, category="jobs", delayLevel=self.getDelayLevel())
        self.jobNameToUse = None

    def getDelayLevel(self):
        return len(DisplayFilter.instance.eventsFromUser) if DisplayFilter.instance else 0

    def alterJobCount(self, value):
        self.jobCountLock.acquire()
        self.jobCount += value
        self.jobCountLock.release()

    def scheduled(self, e):
        jobName = e.getJob().getName().lower()
        self.alterJobCount(1)
        self.logger.debug("Scheduled job '" + jobName + "' jobs = " + repr(self.jobCount))
        if jobName in self.systemJobNames or not e.getJob().isSystem():
            self.logger.debug("Now using job name '" + jobName + "'")
            self.jobNameToUse = jobName
        
        # As soon as we can, we move to the back of the list, so that jobs scheduled in 'done' methods get noticed
        if not e.getJob().isSystem():
            self.afterOthers = True
            Job.getJobManager().removeJobChangeListener(self)
            Job.getJobManager().addJobChangeListener(self)
            self.logger.debug("At back of list now")
        
    @classmethod
    def enable(cls, *args):
        Job.getJobManager().addJobChangeListener(cls(*args))
