#!/usr/bin/env pwsh

$SCRIPT_DIR = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition

pwsh $SCRIPT_DIR/app-create.ps1 `
    && pwsh $SCRIPT_DIR/app-setup.ps1 `
    && pwsh $SCRIPT_DIR/app-copy.ps1
