#!/bin/zsh

# To create the GUI app bundle for gitinspectorgui,
# execute one of the following commands:
# zsh scripts/pyinstall.zsh or scripts/pyinstall.zsh

# ROOT_DIR is the root dir of the repo = the parent dir of the directory of this script
ROOTDIR="${0:A:h:h}"

cd $ROOTDIR && {
    echo Creating GUI app bundle GitinspectorGUI.app for macOS
    echo "Deleting old app directories"
    rm -rf app/* && rm -rf build
    echo
    pyinstaller --distpath=app app-gui-bundle.spec

    if [[ $? -eq 0 ]]; then
        echo
        echo "Done, created GitinspectorGUI.app in folder $ROOTDIR/app"
    fi
}
