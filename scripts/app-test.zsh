#!/bin/zsh

# To create the CLI and GUI apps for gitinspector, and execute all pytests,
# execute this script from the root dir of the repo (parent of this dir):
# scripts/app-tests.sh
# bash app-create-mac.sh && pytest tests

# Do not complain if * does not match anything
setopt +o nomatch

# Clear gitinspectorgui settings file (-f: do not complain if no files to delete).
# Note that also the file gitinspectorgui-path.cfg is deleted, so that the settings
# file path will be restored to its original location.
rm -f ~/Library/"Application Support"/PySimpleGUI/settings/gitinspectorgui*

# ROOT_DIR is the root dir of the repo = the parent dir of the directory of this script
ROOT_DIR="${0:A:h:h}"

cd $ROOT_DIR && zsh scripts/pyinstall.zsh && echo && pytest && {
    echo
    GUIAPP=${ROOT_DIR}"/app/GitinspectorGUI.app"
    echo Opening app $GUIAPP
    open -a $GUIAPP
}
