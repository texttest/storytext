#
# spec file for package python-StoryText
#
# Copyright (c) 2015 SUSE LINUX Products GmbH, Nuernberg, Germany.
#
# All modifications and additions to the file contributed by third parties
# remain the property of their copyright owners, unless otherwise agreed
# upon. The license for this file, and modifications and additions to the
# file, is the same license as for the pristine package itself (unless the
# license for the pristine package is not an Open Source License, in which
# case the license is the MIT License). An "Open Source License" is a
# license that conforms to the Open Source Definition (Version 1.9)
# published by the Open Source Initiative.

# Please submit bugfixes or comments via http://bugs.opensuse.org/


Name:           python-StoryText
Version:        trunk
Release:        0
License:        LGPL
Summary:        An unconvential GUI-testing tool for UIs written with PyGTK, Tkinter, wxPython, Swing, SWT or Eclipse RCP
Url:            http://www.texttest.org/index.php?page=ui_testing
Group:          Development/Languages/Python
Source:         https://pypi.python.org/packages/source/S/StoryText/StoryText-%{version}.tar.gz
BuildRequires:  python-devel
Requires:       python-ordereddict
BuildRoot:      %{_tmppath}/%{name}-%{version}-build
%if 0%{?suse_version} && 0%{?suse_version} <= 1110
%{!?python_sitelib: %global python_sitelib %(python -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}
%else
BuildArch:      noarch
%endif

%description
StoryText is an unconventional GUI testing tool, with support for PyGTK, Tkinter, wxPython, Swing, SWT and Eclipse RCP. Instead of recording GUI mechanics directly, it asks the user for descriptive names and hence builds up a "domain language" along with a "UI map file" that translates it into the current GUI layout. The point is to reduce coupling, allow very expressive tests, and ensure that GUI changes mean changing the UI map file but not all the tests. Instead of an "assertion" mechanism, it auto-generates a log of the GUI appearance and changes to it. The point is then to use that as a baseline for text-based testing, using e.g. TextTest. It also includes support for instrumenting code so that "waits" can be recorded, making it far easier for a tester to record correctly synchronized tests without having to explicitly plan for this.

%prep
%setup -q -n StoryText-%{version}

%build
env FROM_RPM=1 python setup.py build

%install
env FROM_RPM=1 python setup.py install --prefix=%{_prefix} --root=%{buildroot}

%files
%defattr(-,root,root,-)
%{python_sitelib}/*
%{_bindir}/storytext
%{_bindir}/storytext_editor

%changelog
