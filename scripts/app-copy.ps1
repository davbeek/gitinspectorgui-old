# $env:GUI_APP_DIR is an environment variable that should be set in Windows settings. It
# should point to the directory where GitinspectorGUI.exe can be published or be empty.

# ROOT_DIR is the root dir of the repo = the parent dir of the directory of this script
$ROOT_DIR = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)

$SETUP_FILE_BASE = "gitinspectorgui-setup"
$SETUP_FILE = "$SETUP_FILE_BASE.exe"
$SOURCE = "$ROOT_DIR/app/pyinstall-setup/$SETUP_FILE"

$VERSION = Get-Content "$ROOT_DIR/src/gigui/version.txt"

# Get the target directory from the file app-setup-target-dir.txt if it exists.
$TARGET_DIR_FILE = "$ROOT_DIR/scripts/app-setup-target-dir.txt"
if (Test-Path $TARGET_DIR_FILE) {
    $APP_TARGET_DIR = (Get-Content $TARGET_DIR_FILE) + "/"
}
else {
    $APP_TARGET_DIR = "$ROOT_DIR/app/pyinstall-setup/"
}

$TARGET = "$APP_TARGET_DIR$SETUP_FILE_BASE-$VERSION.exe"

# Check if the SOURCE file exists
if (Test-Path "$SOURCE") {
    Copy-Item "$SOURCE" "$TARGET" -Force
    Write-Host "$SOURCE was copied to $TARGET."
}
else {
    Write-Host "$SOURCE does not exist."
    exit 1
}
