#!/bin/zsh

# $GUI_APPS_PATH is an environment variable that should be set in the login shell.
# It should point to the directory from where GitinspectorGUI.dmg can be published and
# must end with a slash or be empty.

# ROOT_DIR is the root dir of the repo = the parent dir of the directory of this script
ROOT_DIR="${0:A:h:h}"

# $PLATFORM = x86_64 for Intel or arm64 for Apple silicon
PLATFORM=$(uname -m)

TARGET_DIR_FILE=$ROOT_DIR/scripts/app-dmg-target-dir.txt
DMG_FILE=GitinspectorGUI.dmg

VERSION="$(<$ROOT_DIR/src/gigui/version.txt)"

cd $ROOT_DIR/app && {
    if [ -e $TARGET_DIR_FILE ]; then
        APP_TARGET_DIR="$(<$TARGET_DIR_FILE)/"
    else
        APP_TARGET_DIR=""
    fi

    # Use (e) flag to expand environment variables in APP_TARGET_DIR
    APP_TARGET_DIR="${(e)APP_TARGET_DIR}"

    # Create the .dmg file using hdiutil
    hdiutil create -volname "GitinspectorGUI" -srcfolder "GitinspectorGUI.app" -ov -format UDZO "$DMG_FILE"

    if [ "$PLATFORM" = "x86_64" ]; then
        TARGET="${APP_TARGET_DIR}GitinspectorGUI-Intel-$VERSION.dmg"
    else
        TARGET="${APP_TARGET_DIR}GitinspectorGUI-AppleSilicon-$VERSION.dmg"
    fi
    mv GitinspectorGUI.dmg "$TARGET"
    echo Moved dmg to: "$TARGET"
} || {
    # No error message needed, because cd will output an error message when it fails
    exit 1
}
