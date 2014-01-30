
""" Eclipse RCP has its own mechanism for background processing
    Hook application events directly into that for synchronisation."""

import logging, os
import storytext.guishared
from storytext.javaswttoolkit.simulator import DisplayFilter
from org.eclipse.core.runtime.jobs import Job, JobChangeAdapter
from threading import Lock, currentThread
from copy import copy

class JobListener(JobChangeAdapter):
    # Add things from customwidgetevents here, if desired...
    systemJobNames = os.getenv("STORYTEXT_SYSTEM_JOB_NAMES", "").split(",")
    timeDelays = {}
    instance = None
    appEventPrefix = "completion of "
    def __init__(self):
        self.jobNamesToUse = {}
        self.jobCount = 0
        self.eventsSeenOtherListener = set()
        self.customUsageMethod = None
        self.jobCountLock = Lock()
        self.logger = logging.getLogger("Eclipse RCP jobs")
        
    def done(self, e):
        storytext.guishared.catchAll(self.lockAndCheck, e, self.__class__.jobDone)
        
    def jobDone(self, e):
        jobName = e.getJob().getName().lower()
        if self.jobCount > 0:
            self.jobCount -= 1
        self.logger.debug("Completed " + ("system" if e.getJob().isSystem() else "non-system") + " job '" + jobName + "' jobs = " + repr(self.jobCount))    
        # We wait for the system to reach a stable state, i.e. no scheduled jobs
        # Would be nice to call Job.getJobManager().isIdle(),
        # but that doesn't count scheduled jobs for some reason
        noScheduledJobs = self.jobCount == 0
        if noScheduledJobs and self.jobNamesToUse:
            self.setComplete()
        
    def setComplete(self):
        for currCat, currJobName in self.jobNamesToUse.items():
            timeDelay = self.timeDelays.get(currJobName, 0.001)
            DisplayFilter.registerApplicationEvent(self.appEventPrefix + currJobName, category=currCat, timeDelay=timeDelay)
        self.jobNamesToUse = {}

    def scheduled(self, e):
        storytext.guishared.catchAll(self.lockAndCheck, e, self.__class__.registerScheduled)
        
    def lockAndCheck(self, e, func):
        self.jobCountLock.acquire()
        if e not in self.eventsSeenOtherListener:
            if self is self.instance:
                func(self, e)
            else:
                self.logger.debug("This event received during transfer, using other listener")
                self.instance.eventsSeenOtherListener.add(e)
                func(self.instance, e)
        else:
            self.logger.debug("Event previously handled during transfer, discarding")
        self.jobCountLock.release()

    def registerScheduled(self, event):
        job = event.getJob()
        parentJob = Job.getJobManager().currentJob()
        jobName = job.getName().lower()
        self.jobCount += 1
        parentJobName = parentJob.getName().lower() if parentJob else ""
        threadName = currentThread().getName()
        category = "jobs_" + threadName
        postfix = ", parent job " + parentJobName if parentJobName else "" 
        self.logger.debug("Scheduled job '" + jobName + "' jobs = " + repr(self.jobCount) + ", thread = " + threadName + postfix)
        if jobName in self.systemJobNames or self.shouldUseJob(job):
            self.logger.debug("Now using job name '" + jobName + "' for category '" + category + "'")
            self.jobNamesToUse[category] = jobName
            self.removeJobName(parentJobName)
            def matchName(eventName, delayLevel):
                return eventName == self.appEventPrefix + parentJobName
            DisplayFilter.removeApplicationEvent(matchName)
            
    def shouldUseJob(self, job):
        return not job.isSystem() or (self.customUsageMethod and self.customUsageMethod(job))
            
    def removeJobName(self, jobName):
        for currCat, currJobName in self.jobNamesToUse.items():
            if currJobName == jobName:
                self.logger.debug("Removing job name '" + jobName + "' for category '" + currCat + "'")
                del self.jobNamesToUse[currCat]
                return        

    def enableListener(self):
        self.logger.debug("Enabling Job Change Listener in thread " + currentThread().getName())
        Job.getJobManager().addJobChangeListener(self)
        
    def transferListener(self):
        self.jobCountLock.acquire()
        # We need to be after all the application's code reacting to the job, so we truly respond when it's finished
        self.logger.debug("Transferring Job Change Listener in thread " + currentThread().getName())
        newListener = copy(self)
        JobListener.instance = newListener
        Job.getJobManager().addJobChangeListener(newListener)
        Job.getJobManager().removeJobChangeListener(self)
        self.jobCountLock.release()    
            
    @classmethod
    def enable(cls, *args):
        if cls.instance:
            cls.instance.transferListener()
        else:
            JobListener.instance = cls(*args)
            cls.instance.enableListener()
