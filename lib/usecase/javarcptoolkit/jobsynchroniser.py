
""" Eclipse RCP has its own mechanism for background processing
    Hook application events directly into that for synchronisation."""

import logging
from usecase import applicationEvent
from org.eclipse.core.runtime.jobs import Job, JobChangeAdapter
from threading import Lock

class JobListener(JobChangeAdapter):
    def __init__(self):
        JobChangeAdapter.__init__(self)
        self.nonSystemEventName = None
        self.jobCount = 0
        self.jobCountLock = Lock()
        self.afterOthers = False
        self.logger = logging.getLogger("Eclipse RCP jobs")
        
    def done(self, e):
        jobName = e.getJob().getName().lower()
        self.alterJobCount(-1)
        self.logger.debug("Completed " + ("system" if e.getJob().isSystem() else "non-system") + " job '" + jobName + "' jobs = " + repr(self.jobCount))
        if not e.getJob().isSystem():
            self.nonSystemEventName = jobName
            
        # We wait for the system to reach a stable state, i.e. no scheduled jobs
        # Would be nice to call Job.getJobManager().isIdle(),
        # but that doesn't count scheduled jobs for some reason
        if self.jobCount == 0 and self.nonSystemEventName: 
            self.setComplete()

    def setComplete(self):
        applicationEvent("completion of " + self.nonSystemEventName)
        self.nonSystemEventName = None

    def alterJobCount(self, value):
        self.jobCountLock.acquire()
        self.jobCount += value
        self.jobCountLock.release()

    def scheduled(self, e):
        jobName = e.getJob().getName().lower()
        self.alterJobCount(1)
        self.logger.debug("Scheduled job '" + jobName + "' jobs = " + repr(self.jobCount))
        # As soon as we can, we move to the back of the list, so that jobs scheduled in 'done' methods get noticed
        if not e.getJob().isSystem():
            self.afterOthers = True
            Job.getJobManager().removeJobChangeListener(self)
            Job.getJobManager().addJobChangeListener(self)
            self.logger.debug("At back of list now")
        
    @classmethod
    def enable(cls):
        Job.getJobManager().addJobChangeListener(cls())
