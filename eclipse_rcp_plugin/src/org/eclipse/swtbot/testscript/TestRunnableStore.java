package org.eclipse.swtbot.testscript;

public class TestRunnableStore {
	private static Runnable testRunnable;
	private static Runnable testSetupRunnable;
	private static Runnable testExitRunnable;

	public static void setTestRunnables(Runnable runnable, Runnable setupRunnable, Runnable exitRunnable) {
		testRunnable = runnable;
		testSetupRunnable = setupRunnable;
		testExitRunnable = exitRunnable;
	}
	public static Runnable getTestRunnable() {
		return testRunnable;
	}
	public static Runnable getTestSetupRunnable() {
		return testSetupRunnable;
	}
	public static Runnable getTestExitRunnable() {
		return testExitRunnable;
	}
}
