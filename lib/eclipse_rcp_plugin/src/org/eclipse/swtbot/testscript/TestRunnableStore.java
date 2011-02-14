package org.eclipse.swtbot.testscript;

public class TestRunnableStore {
	private static Runnable testRunnable;
	private static Runnable testExitRunnable;

	public static void setTestRunnables(Runnable runnable, Runnable exitRunnable) {
		testRunnable = runnable;
		testExitRunnable = exitRunnable;
	}
	public static Runnable getTestRunnable() {
		return testRunnable;
	}
	public static Runnable getTestExitRunnable() {
		return testExitRunnable;
	}
}
