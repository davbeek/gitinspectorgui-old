#!/usr/bin/env pwsh

# SCRIPTDIR is the root dir of the repo = the parent dir of the directory of this script
$SCRIPT_DIR = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host "Generating gitinspector setup file"
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "$SCRIPT_DIR\app-setup.iss"
