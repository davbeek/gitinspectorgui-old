
GitInspectorGUI
===============

Features
--------
The Python ``gitinspectorgui-old`` tool facilitates detailed quantitative analysis
of the contribution of each author to selected repositories.

- Html and Excel backends provide detailed Git statistics:

  - per author
  - per author subdivided by file
  - per file subdivided by author
  - per file

  Output also provides detailed blame information per file. Output lines are
  colored by author, allowing for easy visual inspection and tracking of
  author contributions.

- The GUI and CLI interface have the same options and functionality.

  Executable apps with a GUI interface are available for macOS and Windows.
  Additionally, a Python package can be installed from PyPI. This solution
  works on all platforms that support Python, including Linux.

Installation of GitinspectorGUI for Windows
-------------------------------------------
Download one of the two stand-alone executables for Windows from the `releases
page <https://github.com/davbeek/gitinspectorgui-old/releases>`_. The two versions
are as follows, where ``x.x.x`` is the version number:

- ``win-gitinspectorgui-setup-x.x.x-Arm.exe``
- ``win-gitinspectorgui-setup-x.x.x-Intel.exe``

Select the Arm version for modern systems with a Snapdragon processor and the
Intel version for systems with a traditional Intel processor. When you are not
sure, you probably have an Intel processor. Note that the Intel version also
executes on Arm processors, although much slower because it uses an emulation
mode. The Arm version, on the other hand, does not execute on Intel processors.

Execute the downloaded setup file, and follow the on-screen installation
instructions. The GitinspectorGUI executable will be available under the
program group GitinspectorGUI.

Installation of GitinspectorGUI for macOS
-----------------------------------------

Installation of Git for macOS
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The ``GitinspectorGUI.app`` app requires Git to be present on macOS.
There are multiple ways to install Git for macOS, but they all require the
command line. The easiest way to do this is by using the Miniconda, Anaconda,
Homebrew or MacPorts package manager:

.. list-table::
   :widths: 45 55
   :header-rows: 1
   :class: longtable
   :align: left

   * - Package Manager
     - Installation Command
   * - Conda
     - ``conda install git``
   * - Homebrew
     - ``brew install git``
   * - MacPorts
     - ``sudo port install git``

If you do not use a package manager, Git can be installed as part of the XCode
Command Line Tools via:

``xcode-select --install``

This does not install the (extremely big) complete XCode IDE, and takes "only"
about 1GB.

Installation of the GitinspectorGUI app
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
Download the appropriate dmg file for your hardware. There are two versions for
macOS, where ``x.x.x`` is the version number:

- ``GitinspectorGUI-x.x.x-AppleSilicon.dmg``

- ``GitinspectorGUI-x.x.x-Intel.dmg``



The Apple silicon version is for the new MacBooks with Apple silicon: in 2025,
the M1, M2, M3, M4 and M5 versions. The Intel version is for the old Intel
MacBooks from 2021 or earlier.

Open the downloaded ``dmg`` file by double clicking. This opens a window with
the GitinspectorGUI app and a link to the Applications folder. Drag the
GitinspectorGUI icon onto the Applications folder, so that the app is copied
into this folder. You can then open the GitinspectorGUI app from the
Applications folder.

The first time you open the GitinspectorGUI app, you will get an error message
saying either *"GitinspectorGUI" can't be opened because Apple cannot check it
for malicious software* or *"GitinspectorGUI" can't be opened because it was not
downloaded from the App store*. Dismiss the popup by clicking ``OK``. Go to
``Apple menu > System Preferences``, click ``Security & Privacy``, then click
tab ``General``. Under *Allow apps downloaded from:* you should see in light
grey two tick boxes: one for *App Store* and one for *App Store and identified
developers*. Below that, you should see an additional line:
*"GitinspectorGUI.app"* was blocked from use because it is not from an
identified developer, and after that, a button ``Open Anyway``. Clicking that
button will allow the GitinspectorGUI app to be executed.

Installation of GitinspectorGUI for Linux
-----------------------------------------
We do not yet have binary versions of the GUI for Linux. Currently, for Linux
only the CLI version is available, via PyPI, but the GUI can be started from the
CLI: ``python -m gigui -g``.

Installation of the GitinspectorGUI CLI for Windows, macOS and Linux
--------------------------------------------------------------------

Installation of Git
^^^^^^^^^^^^^^^^^^^
The CLI version requires Git to be available on your system.

- For Windows, installing the GUI will automatically install Git, which can then
  also be used for the CLI version.

- On macOS, if you follow the installation instructions for the GUI, the
  installed Git can also be used by the CLI version. See `Installation of Git
  for macOS`_.

- On Linux, use the package manager of your distribution to install git.

Installation of the CLI via existing versions of Python and pip
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you already have a working Python installation with ``pip``, you can install
the GitinspectorGUI CLI from PyPI via:

``pip install gitinspectorgui-old``

You can then display the gitinspectorgui help info by executing:

``python -m gigui -h``

Note that the program name is ``gitinspectorgui`` in PyPI, but the name of the
actually installed Python package is the abbreviated form ``gigui``.

Installation of the CLI via the UV Python package manager
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

If you do not already have operational versions of Python and ``pip``, we
recommend using the advanced and user-friendly new Python package manager ``uv``
to install GitinspectorGUI. See the ``uv`` website for `installation
instructions <https://docs.astral.sh/uv/getting-started/installation/>`_.

Once you have installed ``uv``, you can run the GitinspectorGUI CLI via:

``uvx gitinspectorgui-old``

UV will automatically install Python if it is not already available on your
system. It will also automatically download and cache
the latest ``gitinspectorgui`` version and execute it. When a new version of
``gitinspectorgui`` is released, all you need to do is execute:

``uvx gitinspectorgui-old@latest``

This will download, cache and execute the latest ``gitinspectorgui`` version.
Subsequent invocations of ``uvx gitinspectorgui-old`` will then use this new
``gitinspectorgui-old`` version.

Using the GitinspectorGUI CLI via UV
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. list-table::
   :widths: 35 60
   :header-rows: 1
   :class: longtable
   :align: left

   * - Command
     - Description
   * - ``uvx gitinspectorgui-old``
     - Show the help info.
   * - ``uvx gitinspectorgui-old -h``
     - Show the help info.
   * - ``uvx gitinspectorgui-old -g``
     - Open the GUI.
   * - ``uvx gitinspectorgui-old -r repodir``
     - Run the program on the ``repodir`` repository and show the result in the
       default system browser.

Documentation
-------------
Extensive online documentation can be found at the `GitinspectorGUI Read the
Docs website <https://gitinspectorgui.readthedocs.io/en/latest/index.html>`_.

Author
------
- Bert van Beek

Contributors
------------
- Jingjing Wang
- Albert Hofkamp
