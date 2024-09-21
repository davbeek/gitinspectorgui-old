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

# Read the version from the version.txt file
VERSION="$(<$ROOT_DIR/src/gigui/version.txt)"

# Define the name of the .dmg file based on the platform and add version number
if [ "$PLATFORM" = "x86_64" ]; then
    DMG_PLATFORM_FILE="GitinspectorGUI-Intel-$VERSION.dmg"
else
    DMG_PLATFORM_FILE="GitinspectorGUI-AppleSilicon-$VERSION.dmg"
fi

cd $ROOT_DIR/app && {
    # Read the target directory from the file
    APP_TARGET_DIR="$(<$TARGET_DIR_FILE)"

    # Use (e) flag to expand environment variables in APP_TARGET_DIR
    APP_TARGET_DIR="${(e)APP_TARGET_DIR}"

    # Create the .dmg file using hdiutil
    hdiutil create -volname "GitinspectorGUI" -srcfolder "GitinspectorGUI.app" \
        -ov -format UDZO "$DMG_PLATFORM_FILE"

    if [ -e "$TARGET_DIR_FILE" ]; then
        if [ -d "$APP_TARGET_DIR" ]; then
            cp $DMG_PLATFORM_FILE "$APP_TARGET_DIR"
            echo Copied dmg to: "$APP_TARGET_DIR"
        else
            echo "Error: The target directory $APP_TARGET_DIR does not exist."
            exit 1
        fi
    fi
} || {
    # No error message needed, because cd will output an error message when it fails
    exit 1
}
