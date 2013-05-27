
""" Eclipse RCP has its own mechanism for background processing
    Hook application events directly into that for synchronisation."""

import logging, os
import storytext.guishared
from storytext.javaswttoolkit.simulator import DisplayFilter
from org.eclipse.core.runtime.jobs import Job, JobChangeAdapter
from threading import Lock

class JobListener(JobChangeAdapter):
    # Add things from customwidgetevents here, if desired...
    systemJobNames = os.getenv("STORYTEXT_SYSTEM_JOB_NAMES", "").split(",")
    instance = None
    def __init__(self):
        self.jobNameToUse = None
        self.jobCount = 0
        self.jobCountLock = Lock()
        self.logger = logging.getLogger("Eclipse RCP jobs")
        
    def done(self, e):
        storytext.guishared.catchAll(self.jobDone, e)
        
    def jobDone(self, e):
        jobName = e.getJob().getName().lower()
        self.jobCountLock.acquire()
        self.jobCount -= 1
        self.logger.debug("Completed " + ("system" if e.getJob().isSystem() else "non-system") + " job '" + jobName + "' jobs = " + repr(self.jobCount))    
        # We wait for the system to reach a stable state, i.e. no scheduled jobs
        # Would be nice to call Job.getJobManager().isIdle(),
        # but that doesn't count scheduled jobs for some reason
        noScheduledJobs = self.jobCount == 0
        self.jobCountLock.release()        
        if noScheduledJobs and self.jobNameToUse: 
            self.setComplete()

    def setComplete(self):
        DisplayFilter.registerApplicationEvent("completion of " + self.jobNameToUse, category="jobs")
        self.jobNameToUse = None

    def scheduled(self, e):
        storytext.guishared.catchAll(self.jobScheduled, e)
        
    def jobScheduled(self, e):
        self.jobCountLock.acquire()
        jobName = e.getJob().getName().lower()
        self.jobCount += 1
        parentJob = Job.getJobManager().currentJob()
        parentJobName = parentJob.getName().lower() if parentJob else ""
        postfix = ", parent job " + parentJobName if parentJobName else "" 
        self.logger.debug("Scheduled job '" + jobName + "' jobs = " + repr(self.jobCount) + postfix)
        if (jobName in self.systemJobNames or not e.getJob().isSystem()) and (not self.jobNameToUse or not parentJobName or self.jobNameToUse == parentJobName):
            self.logger.debug("Now using job name '" + jobName + "'")
            self.jobNameToUse = jobName
        
        # As soon as we can, we move to the back of the list, so that jobs scheduled in 'done' methods get noticed
        if not e.getJob().isSystem():
            Job.getJobManager().removeJobChangeListener(self)
            Job.getJobManager().addJobChangeListener(self)
            self.logger.debug("At back of list now")
        self.jobCountLock.release()
            
    @classmethod
    def enable(cls, *args):
        cls.instance = cls(*args)
        cls.instance.logger.debug("Enabling Job Change Listener")
        Job.getJobManager().addJobChangeListener(cls.instance)
