# GitInspectorGUI

## Features
The Python ``gitinspectorgui`` tool facilitates detailed quantitative analysis
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

- Executable apps with GUI interface are available for macOS and Windows. In
  addition, a Python package can be installed from PyPI.

## Download and installation
### GUI
Stand-alone executables for Windows and macOS can be downloaded from the
[releases page](https://github.com/davbeek/gitinspectorgui/releases).

#### Windows
Download the setup file, execute it, and follow the on-screen installation
instructions. The GitinspectorGUI executable will be available under the
program group GitinspectorGUI.

#### macOS

Download the appropriate dmg file for your hardware. There are two versions for macOS:

- **macOS Intel**: This version is for the old Intel MacBooks.

- **macOS Apple-Silicon**: This version is for the newer MacBooks with Apple
  silicon. Currently the M1, M2, M3 and M4 versions.

Open the downloaded file by double clicking. This opens a window with the
GitinspectorGUI app. Drag the icon onto the Applications folder or to a
temporary folder, from where it can be moved to the Applications folder. You can
then open the GitinspectorGUI app from the Applications folder.

The first time you open the GitinspectorGUI app, you will get an error message
saying either *"GitinspectorGUI" can't be opened because Apple cannot check it
for malicious software* or *"GitinspectorGUI" can't be opened because it was not
downloaded from the App store*. Dismiss the popup by clicking `OK`. Go to `Apple
menu > System Preferences`, click `Security & Privacy`, then click tab
`General`. Under *Allow apps downloaded from:* you should see in light grey two
tick boxes: one for *App Store* and one for *App Store and identified
developers*. Below that, you should see an additional line:
*"GitinspectorGUI.app"* was blocked from use because it is not from an
identified developer, and after that, a button `Open Anyway`. Clicking that
button will allow the GitinspectorGUI app to be executed.

### CLI
For CLI versions, you need to have a working Python installation, so that you
can install GitinspectorGUI from PyPI via `pip install gitinspectorgui`. You can
then execute the program by running `python -m gigui -h` to display the help
info in the CLI. Note that the program name is gitinspectorgui in PyPI, but the
name of the actually installed Python package is the abbreviated form `gigui`.

## Documentation
Extensive online documentation can be found at the [GitinspectorGUI Read the
Docs website](https://gitinspectorgui.readthedocs.io/en/latest/index.html).

## Contributors
- Bert van Beek
- Jingjing Wang
- Albert Hofkamp
