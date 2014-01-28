package org.eclipse.swtbot.testscript;

import java.lang.reflect.InvocationTargetException;

import org.eclipse.core.runtime.Assert;
import org.eclipse.core.runtime.CoreException;
import org.eclipse.core.runtime.IConfigurationElement;
import org.eclipse.core.runtime.IExtension;
import org.eclipse.core.runtime.IProduct;
import org.eclipse.core.runtime.Platform;
import org.eclipse.equinox.app.IApplication;
import org.eclipse.equinox.app.IApplicationContext;
import org.eclipse.ui.PlatformUI;
import org.eclipse.ui.testing.ITestHarness;
import org.eclipse.ui.testing.TestableObject;


/**
 * Copied from the headless test runner: the point here is to support running dynamic language scripts, 
 * particularly PyUseCase from Jython. The basic operation is that these scripts should derived something
 * from java.lang.Runnable, call TestRunnableStore.setTestRunnable(runner) and then start Eclipse.
 */
public class Application implements IApplication, ITestHarness {

	private static final String	DEFAULT_APP_3_0	= "org.eclipse.ui.ide.workbench";	//$NON-NLS-1$
	
	private TestableObject		fTestableObject;
	private IApplication		fApplication;

	/*
	 * (non-Javadoc)
	 * @see org.eclipse.equinox.app.IApplication#start(org.eclipse.equinox.app.IApplicationContext)
	 */
	public Object start(IApplicationContext context) throws Exception {
		String[] args = (String[]) context.getArguments().get(IApplicationContext.APPLICATION_ARGS);
		Object app = getApplication(args);

		Assert.isNotNull(app);

		fTestableObject = PlatformUI.getTestableObject();
		fTestableObject.setTestHarness(this);
		if (app instanceof IApplication) {
			fApplication = (IApplication) app;
			Object ret = fApplication.start(context);
			Runnable exitRunnable = Application.getRunnable("getTestExitRunnable");
			if (exitRunnable != null) 
				exitRunnable.run();
			return ret;
		}
		throw new IllegalArgumentException("Could not execute application " + getApplicationToRun(args));
	}

	/*
	 * (non-Javadoc)
	 * @see org.eclipse.equinox.app.IApplication#stop()
	 */
	public void stop() {
		if (fApplication != null)
			fApplication.stop();
	}

	/*
	 * return the application to run, or null if not even the default application is found.
	 */
	private Object getApplication(String[] args) throws CoreException {
		// Find the name of the application as specified by the PDE JUnit launcher.
		// If no application is specified, the 3.0 default workbench application
		// is returned.
		IExtension extension = Platform.getExtensionRegistry().getExtension(Platform.PI_RUNTIME, Platform.PT_APPLICATIONS,
				getApplicationToRun(args));

		Assert.isNotNull(extension);

		// If the extension does not have the correct grammar, return null.
		// Otherwise, return the application object.
		IConfigurationElement[] elements = extension.getConfigurationElements();
		if (elements.length > 0) {
			IConfigurationElement[] runs = elements[0].getChildren("run"); //$NON-NLS-1$
			if (runs.length > 0) {
				Object runnable = runs[0].createExecutableExtension("class"); //$NON-NLS-1$
				if (runnable instanceof IApplication)
					return runnable;
			}
		}
		return null;
	}

	/*
	 * The -testApplication argument specifies the application to be run. If the PDE JUnit launcher did not set this
	 * argument, then return the name of the default application. In 3.0, the default is the
	 * "org.eclipse.ui.ide.worbench" application.
	 */
	private String getApplicationToRun(String[] args) {
		IProduct product = Platform.getProduct();
		if (product != null)
			return product.getApplication();
		return getArgument(args, "-testApplication", DEFAULT_APP_3_0);
	}

	private String getArgument(String[] args, String argName, String defaultValue) {
		for (int i = 0; i < args.length; i++)
			if (args[i].equals(argName) && (i < args.length - 1)) //$NON-NLS-1$
				return args[i + 1];
		return defaultValue;
	}
	
	static Runnable getRunnable(String methodName) throws ClassNotFoundException, IllegalArgumentException, SecurityException, IllegalAccessException, InvocationTargetException, NoSuchMethodException {
		Class storeClass = ClassLoader.getSystemClassLoader().loadClass("org.eclipse.swtbot.testscript.TestRunnableStore");
		return (Runnable)storeClass.getMethod(methodName).invoke(null);
	}

	/*
	 * (non-Javadoc)
	 * @see org.eclipse.ui.testing.ITestHarness#runTests()
	 */
	public void runTests() {
		fTestableObject.testingStarting();
		try {
			Runnable testRunnable = Application.getRunnable("getTestRunnable");
			if (testRunnable != null)
				testRunnable.run();
		} catch (Exception e) {
			e.printStackTrace();
		}
		// This terminates the application, and we don't want to do that: rely on the tests to fix that for us
		//fTestableObject.testingFinished();
	}	
}
