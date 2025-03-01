# GitInspectorGUI

## Features

The Python `gitinspectorgui` tool facilitates detailed quantitative analysis
of the contribution of each author to selected repositories.

-   Html and Excel backends provide detailed Git statistics:

    -   per author
    -   per author subdivided by file
    -   per file subdivided by author
    -   per file

    Output also provides detailed blame information per file. Output lines are
    colored by author, allowing for easy visual inspection and tracking of
    author contributions.

-   The GUI and CLI interface have the same options and functionality.

    Executable apps with a GUI interface are available for macOS and Windows.
    Additionally, a Python package can be installed from PyPI. This solution
    works on all platforms that support Python, including Linux.

## Installation of GitinspectorGUI for Windows

### Installation of Git for Windows

The GitinspectorGUI app is only about 18MB in size, but it requires Git for
Windows to be available on your system. Git for Windows is around 375MB in
size and can be downloaded from
[git-scm.com](https://git-scm.com/downloads/win).

Git for Windows presents numerous questions during installation. For users
unfamiliar with Git, these questions can seem overwhelming. However, leaving
all options at their default settings will ensure proper functionality. A
drawback of using the default settings is that it may add extra context menu
items in File Explorer.

### Installation of the GitinspectorGUI executable

Download the stand-alone executable `windows-gitinspectorgui-setup.exe` from the
[releases page](https://github.com/davbeek/gitinspectorgui/releases). Execute
it, and follow the on-screen installation instructions. The GitinspectorGUI
executable will be available under the program group GitinspectorGUI.

### Recommended browser

Firefox is recommended to display analysis output. Microsoft Edge works properly
only when analysis output is generated in html files. We have not tested Chrome.

## Installation of GitinspectorGUI for macOS

### Installation of Git

There are multiple ways to install Git for macOS, but they all require the
command line. The easiest way to do this is by using the Miniconda or Anaconda,
Homebrew or MacPorts package manager:

-   Conda:
    `conda install git`

-   Homebrew:
    `brew install git`

-   MacPorts:
    `sudo port install git`

If you do not use a package manager, Git can be installed as part of the XCode
Command Line Tools via:

`xcode-select --install`

This does not install the complete XCode IDE and takes about 1GB.

### Installation of the GitinspectorGUI app

Download the appropriate dmg file for your hardware. There are two versions for
macOS:

-   **macOS Intel**: This version is for the old Intel MacBooks.

-   **macOS Apple-Silicon**: This version is for the newer MacBooks with Apple
    silicon. Currently the M1, M2, M3 and M4 versions.

Open the downloaded file by double clicking. This opens a window with the
GitinspectorGUI app. Drag the icon onto the Applications folder or to a
temporary location, from where it can be moved to the Applications folder. You
can then open the GitinspectorGUI app from the Applications folder.

The first time you open the GitinspectorGUI app, you will get an error message
saying either _"GitinspectorGUI" can't be opened because Apple cannot check it
for malicious software_ or _"GitinspectorGUI" can't be opened because it was not
downloaded from the App store_. Dismiss the popup by clicking `OK`. Go to `Apple
menu > System Preferences`, click `Security & Privacy`, then click tab
`General`. Under _Allow apps downloaded from:_ you should see in light grey two
tick boxes: one for _App Store_ and one for _App Store and identified
developers_. Below that, you should see an additional line:
_"GitinspectorGUI.app"_ was blocked from use because it is not from an
identified developer, and after that, a button `Open Anyway`. Clicking that
button will allow the GitinspectorGUI app to be executed.

## Installation of GitinspectorGUI for Linux

We do not yet have binary versions of the GUI for Linux, but we aim to provide
binaries for some of the biggest Linux distros in the future. Currently, for
Linux only the CLI version is available.

# Installation of the GitinspectorGUI CLI for Windows, macOS and Linux

## Via existing versions of Python and pip

If you already have a working Python installation with `pip`, you can install
the GitinspectorGUI CLI from PyPI via:

`pip install gitinspectorgui`

You can then display the gitinspectorgui help info by executing:

`python -m gigui -h`

Like the GUI app, the CLI version also requires Git to be installed.

Note that the program name is `gitinspectorgui` in PyPI, but the name of the
actually installed Python package is the abbreviated form `gigui`.

## Via the UV Python package manager

If you do not already have operational versions of Python and `pip`, we
recommend using the advanced and user-friendly new Python package manager `uv`
to install GitinspectorGUI. See the `uv` website for [installation
instructions](https://docs.astral.sh/uv/getting-started/installation/).

Once you have installed `uv`, you can run the GitinspectorGUI CLI via:

`uvx gitinspectorgui`

UV will automatically install Python if it is not already avaiable on your
system. It will also automatically download and cache
the latest `gitinspectorgui` version and execute it. When a new version of
`gitinspectorgui` is released, all you need to do is execute:

`uvx gitinspectorgui@latest`

This will download, cache and execute the latest `gitinspectorgui` version.
Subsequent invocations of `uvx gitinspectorgui` will then use this new
`gitinspectorgui` version.

## Using the CLI

-   `uvx gitinspectorgui -h` show the help info.
-   `uvx gitinspectorgui -g` opens the GUI.
-   `uvx gitinspectorgui -r repodir` runs the program on the repodir repository
    and shows the result in the default system browser.

## Documentation

Extensive online documentation can be found at the [GitinspectorGUI Read the
Docs website](https://gitinspectorgui.readthedocs.io/en/latest/index.html).

## Author

-   Bert van Beek

## Contributors

-   Jingjing Wang
-   Albert Hofkamp
