Summary of what it is:

        The full documentation is present at http://www.texttest.org/index.php?page=ui_testing
        What follows is just a brief summary.

        StoryText (formerly known as PyUseCase) is a record/replay layer for Python GUIs. 
        It currently has extensive support for PyGTK GUIs
        (including a proof of concept for the hildon extension), and beta status support for Swing, SWT/Eclipse RCP/GEF and 
        Tkinter, and wxPython GUIs. Besides providing a mechanism for recording and 
        playing back UI interaction, it also generates a log of the UI appearance. 
        On UNIX-based systems it can also be useful on console programs to record and simulate signals 
        received by the process.

        The aim is only to simulate the interactive actions of a user, not to verify correctness of a program
        as such. The log produced should form a good basis for textual testing though, using a tool like
        TextTest, also available from SourceForge. It has been developed together with TextTest and is essentially intended
        to be used in conjunction with it.

        To summarise, the motivation for it is that traditional record/replay tools, besides being expensive,
        tend to record very low-level scripts that are a nightmare to maintain and can only be read by developers.
        This is in large part because they record the GUI mechanics rather than the intent behind the test. (Even
        though this is usually in terms of widgets not pixels now)

        StoryText is built around the idea of recording in a domain language
        by maintaining a mapping between the actions that can be performed with the UI and
        names that describe what the point of these actions is. This incurs a small extra setup cost of course,
        but it has the dual benefit of making the tests much more readable and much more resilient to future
        UI changes than if they are recorded in a more programming-language-like script.

        Another key advantage over other approaches is that, with some very simple instrumentation in the code,
        it is easy to tell StoryText where the script will need to wait, thus allowing it to record "wait"
        statements without the test writer having to worry about it. This is otherwise a common headache
        for recorded tests: most other tools require you to explicitly synchronise the test when writing it (external
        to the recording).

        Example recorded usecase ("test script") for a flight booking system:

        wait for flight information to load
        select flight SA004
        proceed to book seats
        # SA004 is full...
        accept error message
        quit

System requirements:

    At least Python 2.5 (Jython 2.5 for the Java UIs)
    At least PyGTK 2.12 for the PyGTK part
    Python 3.x supported only for Tkinter UIs currently

Other Open Source Software packaged with it/used by it:

    ordereddict.py  : sequential dictionaries. (Raymond Hettinger, v1.1)

Installation:

    Go to the "source" directory and run "python setup.py install". To sort out dependencies and so on, read the docs
    at http://www.texttest.org/index.php?page=ui_testing&n=storytext_download

Documentation:

    http://www.texttest.org/index.php?page=ui_testing

Examples and tests:

    A simple "video store" PyGTK GUI is provided to give an example usage in the "examples" directory. 
    It's basically an ordinary PyGTK app with the shortcut bar included. You can for example do
 
    storytext -r my_script.txt videostore.py

    will record a high-level use case to my_script.txt, based on whatever you do. This can
    then be replayed via

    storytext -p my_script.txt videostore.py

    The complete test suite (which uses Texttest) is also provided under "tests", this has a wealth of little GUIs
    illustrating the support for the various widgets. It should be possible to run it via texttest.py -d <path to tests>
    (if you install TextTest, of course)

Bugs/Support:
    
    Write to the general mailing list at texttest-users@lists.sourceforge.net
    Report bugs in the Launchpad bugtracker at https://bugs.launchpad.net/storytext
