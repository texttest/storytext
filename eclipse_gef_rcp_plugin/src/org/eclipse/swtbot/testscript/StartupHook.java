package org.eclipse.swtbot.testscript;

import org.eclipse.ui.IStartup;

public class StartupHook implements IStartup {

	@Override
	public void earlyStartup() {
		// TODO Auto-generated method stub
		Runnable setupRunnable;
		try {
			setupRunnable = Application.getRunnable("getTestSetupRunnable");
			if (setupRunnable != null) 
				setupRunnable.run();

		} catch (Exception e) {
			// TODO Auto-generated catch block
			e.printStackTrace();
		} 		
	}

}
