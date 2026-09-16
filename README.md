# EXE Combine Tool

## Overview

The **EXE Combine Tool** is a Python-based utility that allows users to merge two executable files (`.exe`) into a single executable. When the combined executable is run, both embedded EXE files are extracted and executed simultaneously. The tool provides a simple graphical user interface (GUI) for easy selection of EXE files, along with the option to choose an icon for the output executable.

---

## Terms of Service (TOS)

**By using this tool, you agree to the following terms:**

1. **Non-Malicious Use**: This tool is strictly intended for legitimate, non-malicious purposes. You agree not to use this tool for:
   - Creating malware, viruses, or any form of harmful software.
   - Embedding malicious content into legitimate executables.
   - Distributing harmful software or engaging in illegal cyber activities.
   - Hiding or disguising dangerous software inside other executables without the user's consent.

2. **Responsibility**: The creators of this tool are not responsible for any damages, illegal activity, or malicious use arising from its use. You bear full responsibility for any action you take with this software.

3. **Respect for Others**: You agree not to use this tool in a way that violates the privacy, security, or rights of others.

**If you do not agree with these terms, you are prohibited from using this tool.**

---

## Features

### Original
- **Combine Two EXE Files**: Easily select two `.exe` files to be merged into one.
- **Icon Selection**: Choose the output executable's icon from:
  - EXE 1's icon
  - EXE 2's icon
  - A custom icon (`.ico` file)
- **GUI Interface**: Simple and intuitive interface for selecting files and configuring the output.
- **Standalone Output**: The combined EXE runs both files without needing the original files to exist.

### Added
- **Assembly Information Window**: A dedicated modal dialog to edit the output executable's metadata (Product Name, Description, Company Name, Copyright, Trademarks, Original Filename, Product Version, File Version).
- **Load Metadata from EXE**: Buttons "Load from EXE 1" and "Load from EXE 2" read the existing Version Info from either input file via `pefile` and auto-fill all metadata fields.
- **File Date Management**: Optional post-build modification of the output executable's Created / Modified / Accessed timestamps.
  - Accepted formats: `YYYY-MM-DD HH:MM:SS`, `YYYY-MM-DD HH:MM`, `YYYY-MM-DD`.
  - Empty field = leave that timestamp unchanged.
- **No console**: Combined exe is now running without opening console.
---

## How to Use the Tool

### Requirements

- **Python 3.x** installed on your system.
- **PyInstaller** installed via `pip install pyinstaller`.
- **PyInstaller-versionfile** installed via `pip install pyinstaller-versionfile`.
- **PeFile** installed via `pip install pefile`.

### Installation

1. Clone or download this repository.
2. Install the required dependencies by running:
   ```bash
   pip install pyinstaller
   pip install pyinstaller-versionfile
   pip install pefile


