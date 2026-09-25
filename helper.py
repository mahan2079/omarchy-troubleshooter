#!/usr/bin/env python3
import sys
import os
import json
import argparse
import subprocess
import time
import tempfile
import stat
import shutil

DATA_FILE = os.path.expanduser("~/.config/omarchy/troubleshooter-log.json")
SEQ_DATA_FILE = os.path.expanduser("~/.config/omarchy/troubleshooter-sequences.json")

def get_secure_temp_dir():
    # Prefer XDG_RUNTIME_DIR (/run/user/<uid>) which is a user-private tmpfs (mode 0700)
    base_run = os.environ.get("XDG_RUNTIME_DIR")
    if base_run and os.path.isdir(base_run):
        secure_dir = os.path.join(base_run, "omarchy", "troubleshooter", "recipes")
    else:
        # Fallback to private user config cache
        secure_dir = os.path.expanduser("~/.local/state/omarchy/troubleshooter/recipes")
    os.makedirs(secure_dir, mode=0o700, exist_ok=True)
    return secure_dir

DEFAULT_ISSUES = [
    {
        "id": "audio-crackling",
        "title": "Audio Crackling / PipeWire Desync",
        "category": "Audio",
        "tags": ["audio", "pipewire", "wireplumber", "sound"],
        "description": "Sound produces crackling, latency, or suddenly cuts off on output devices.",
        "solution": "Restart user PipeWire services or clear pipewire-pulse state.",
        "prompt": "Fix audio crackling and PipeWire/WirePlumber sync issues on this Omarchy system. Check status of pipewire, pipewire-pulse, and wireplumber systemd user units, inspect logs for buffer underruns, and apply the required fix."
    },
    {
        "id": "hyprland-monitor-glitch",
        "title": "Monitor / Workspace Layout Glitch",
        "category": "Display",
        "tags": ["hyprland", "monitors", "display", "workspace"],
        "description": "Displays out of alignment or workspaces stuck after reconnecting external monitors.",
        "solution": "Reload Hyprland config and check ~/.config/hypr/monitors.lua.",
        "prompt": "Investigate and fix the monitor / workspace layout glitch in Hyprland. Check `hyprctl monitors`, validate `~/.config/hypr/monitors.lua`, and run `hyprctl reload`."
    },
    {
        "id": "bluetooth-headphones",
        "title": "Bluetooth Device Connected But No Sound",
        "category": "Bluetooth",
        "tags": ["bluetooth", "audio", "headset", "a2dp"],
        "description": "Bluetooth headphones connect but fail to switch profile to A2DP or audio output stays on default sink.",
        "solution": "Switch default sink using wpctl or restart bluetooth.service.",
        "prompt": "Troubleshoot Bluetooth audio connection. Check `bluetoothctl info`, `wpctl status`, verify default audio sink, set the default sink to the active Bluetooth audio device, and fix any codec/profile negotiation failures."
    },
    {
        "id": "omarchy-shell-widget",
        "title": "Omarchy Shell Bar / Widget Reload",
        "category": "Shell",
        "tags": ["omarchy", "shell", "bar", "quickshell"],
        "description": "Top bar widget frozen, layout missing an element, or quickshell error.",
        "solution": "Rescan plugins with `omarchy-shell shell rescanPlugins` or restart shell.",
        "prompt": "Diagnose and fix the Omarchy top bar / Quickshell issue. Check `~/.config/omarchy/shell.json`, inspect Quickshell logs, and rescan or restart `omarchy-shell`."
    },
    {
        "id": "pacman-db-lock",
        "title": "Pacman DB Lock / Keyring Errors",
        "category": "Packages",
        "tags": ["pacman", "arch", "aur", "update"],
        "description": "System update failed due to /var/lib/pacman/db.lck or expired Arch keyring signatures.",
        "solution": "Check if pacman process is running; if not remove stale lock and refresh archlinux-keyring.",
        "prompt": "Resolve package manager issue on Arch Linux / Omarchy. Check for stale `/var/lib/pacman/db.lck`, verify keyring status with `archlinux-keyring`, and fix any package conflict or lock error."
    }
]

DEFAULT_SEQUENCES = [
    {
        "id": "seq-update-arch",
        "title": "Full System Refresh & Update",
        "category": "Maintenance",
        "tags": ["update", "pacman", "aur"],
        "description": "Refresh keyring and run omarchy update",
        "commands": "sudo pacman -Sy archlinux-keyring\nomarchy update"
    },
    {
        "id": "seq-reset-audio",
        "title": "Reset Audio Subsystem (PipeWire)",
        "category": "Audio",
        "tags": ["pipewire", "audio", "reset"],
        "description": "Restart all pipewire layers in order.",
        "commands": "systemctl --user restart pipewire pipewire-pulse wireplumber\nsleep 1\nwpctl status"
    },
    {
        "id": "seq-reconnect-bt",
        "title": "Restart Bluetooth Service",
        "category": "Bluetooth",
        "tags": ["bluetooth", "service"],
        "description": "Completely restart the bluetooth daemon.",
        "commands": "sudo systemctl restart bluetooth\nsleep 2\nbluetoothctl show"
    }
]

def load_data():
    if not os.path.exists(DATA_FILE):
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        save_data(DEFAULT_ISSUES)
        return DEFAULT_ISSUES
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_ISSUES

def save_data(data):
    parent_dir = os.path.dirname(DATA_FILE)
    os.makedirs(parent_dir, exist_ok=True)
    # Atomic write to avoid partial/corrupted writes
    fd, tmp_path = tempfile.mkstemp(prefix="issues-", suffix=".json.tmp", dir=parent_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, DATA_FILE)

def load_seq_data():
    if not os.path.exists(SEQ_DATA_FILE):
        os.makedirs(os.path.dirname(SEQ_DATA_FILE), exist_ok=True)
        save_seq_data(DEFAULT_SEQUENCES)
        return DEFAULT_SEQUENCES
    try:
        with open(SEQ_DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_SEQUENCES

def save_seq_data(data):
    parent_dir = os.path.dirname(SEQ_DATA_FILE)
    os.makedirs(parent_dir, exist_ok=True)
    # Atomic write
    fd, tmp_path = tempfile.mkstemp(prefix="seqs-", suffix=".json.tmp", dir=parent_dir)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.chmod(tmp_path, 0o600)
    os.replace(tmp_path, SEQ_DATA_FILE)

def run_agent_prompt(prompt_text):
    cmd = ["omarchy-launch-terminal", "opencode", "--prompt", prompt_text]
    try:
        subprocess.Popen(cmd, start_new_session=True)
        return True
    except Exception:
        try:
            subprocess.Popen(["xdg-terminal-exec", "opencode", "--prompt", prompt_text], start_new_session=True)
            return True
        except Exception:
            return False

def cmd_list(args):
    data = load_data()
    print(json.dumps(data))

def cmd_add(args):
    data = load_data()
    new_id = f"issue-{int(time.time())}"
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    item = {
        "id": new_id,
        "title": args.title,
        "category": args.category or "General",
        "tags": tags,
        "description": args.description or "",
        "solution": args.solution or "",
        "prompt": args.prompt or f"Fix the issue: {args.title}. Details: {args.description}. Known solution: {args.solution}"
    }
    data.insert(0, item)
    save_data(data)
    print(json.dumps({"success": True, "id": new_id}))

def cmd_delete(args):
    data = load_data()
    data = [x for x in data if x.get("id") != args.id]
    save_data(data)
    print(json.dumps({"success": True}))

def cmd_launch(args):
    data = load_data()
    target = next((x for x in data if x.get("id") == args.id), None)
    if not target:
        print(json.dumps({"success": False, "error": "Item not found"}))
        return

    base_prompt = target.get("prompt", "")
    if not base_prompt:
        base_prompt = f"Fix the issue: {target.get('title')}. Details: {target.get('description')}. Known solution: {target.get('solution')}"

    if args.custom_note:
        full_prompt = f"[CONTEXT / LOGGED ISSUE]\nTitle: {target.get('title')}\nCategory: {target.get('category')}\nTags: {', '.join(target.get('tags', []))}\nKnown fix/details: {target.get('solution')}\n\n[USER CURRENT SYMPT / NOTE]\n{args.custom_note}\n\nPlease diagnose and apply the fix on this PC following the instructions above."
    else:
        full_prompt = f"[CONTEXT / LOGGED ISSUE]\nTitle: {target.get('title')}\nCategory: {target.get('category')}\nTags: {', '.join(target.get('tags', []))}\nKnown fix/details: {target.get('solution')}\nInstructions: {base_prompt}\n\nPlease diagnose and apply the fix on this PC."

    run_agent_prompt(full_prompt)
    print(json.dumps({"success": True}))

def cmd_launch_custom(args):
    full_prompt = f"[USER PC ISSUE REPORT]\nCategory: {args.category or 'General'}\nTags: {args.tags or ''}\nIssue: {args.issue}\n\nPlease diagnose the cause on this Omarchy Arch Linux system, check relevant logs and configs, and fix it properly."
    
    if args.save:
        data = load_data()
        new_id = f"issue-{int(time.time())}"
        tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
        item = {
            "id": new_id,
            "title": args.issue[:50],
            "category": args.category or "General",
            "tags": tags,
            "description": args.issue,
            "solution": "",
            "prompt": full_prompt
        }
        data.insert(0, item)
        save_data(data)

    run_agent_prompt(full_prompt)
    print(json.dumps({"success": True}))

# Sequence commands
def cmd_list_seq(args):
    data = load_seq_data()
    print(json.dumps(data))

def cmd_add_seq(args):
    data = load_seq_data()
    new_id = f"seq-{int(time.time())}"
    tags = [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else []
    item = {
        "id": new_id,
        "title": args.title,
        "category": args.category or "General",
        "tags": tags,
        "description": args.description or "",
        "commands": args.commands or "echo 'No commands configured'"
    }
    data.insert(0, item)
    save_seq_data(data)
    print(json.dumps({"success": True, "id": new_id}))

def cmd_del_seq(args):
    data = load_seq_data()
    data = [x for x in data if x.get("id") != args.id]
    save_seq_data(data)
    print(json.dumps({"success": True}))

def cmd_run_seq(args):
    data = load_seq_data()
    target = next((x for x in data if x.get("id") == args.id), None)
    if not target:
        print(json.dumps({"success": False, "error": "Sequence not found"}))
        return

    cmds = target.get("commands", "")
    title = target.get("title", "Shell Recipe")
    category = target.get("category", "General")
    tags = ", ".join(target.get("tags", []))

    # Secure exclusive temporary script creation in private directory
    secure_dir = get_secure_temp_dir()
    script_fd, script_path = tempfile.mkstemp(prefix="omarchy-recipe-", suffix=".sh", dir=secure_dir, text=True)
    
    cmd_lines = [l.strip() for l in cmds.split("\n") if l.strip()]

    with os.fdopen(script_fd, 'w', encoding='utf-8') as f:
        f.write("#!/bin/bash\n")
        f.write("set -euo pipefail\n")
        f.write("trap 'rm -f \"$0\"' EXIT\n")
        f.write("clear\n")
        f.write("echo -e '\\033[1;36m=====================================================\\033[0m'\n")
        f.write(f"echo -e '\\033[1;36m  SHELL RECIPE: {title}\\033[0m'\n")
        f.write(f"echo -e '\\033[0;34m  Category: {category}  |  Tags: {tags}\\033[0m'\n")
        f.write("echo -e '\\033[1;36m=====================================================\\033[0m'\n\n")
        f.write("echo -e '\\033[1;37mCommands to execute:\\033[0m'\n")
        
        for idx, line in enumerate(cmd_lines, 1):
            safe_l = line.replace("'", "'\\''")
            f.write(f"echo -e '  \\033[1;33m{idx}.\\033[0m {safe_l}'\n")
            
        f.write("\necho -e '\\033[1;36m-----------------------------------------------------\\033[0m'\n")
        f.write("echo -e '\\033[1;32mPress [ENTER] to execute these commands, or Ctrl+C to cancel...\\033[0m'\n")
        f.write("read -r\n\n")
        
        for idx, line in enumerate(cmd_lines, 1):
            if line.startswith("#"):
                f.write(f"{line}\n")
                continue
            safe_l = line.replace("'", "'\\''")
            f.write(f"echo -e '\\n\\033[1;35m>> [{idx}/{len(cmd_lines)}] Running: {safe_l}\\033[0m'\n")
            f.write(f"{line}\n")
            f.write("echo -e '\\033[0;32m   ✓ Step finished.\\033[0m'\n")
            
        f.write("\necho -e '\\n\\033[1;32m=====================================================\\033[0m'\n")
        f.write("echo -e '\\033[1;32m  ✓ All recipe commands completed.\\033[0m'\n")
        f.write("echo -e '\\033[1;32m=====================================================\\033[0m'\n")
        f.write("echo -e '\\033[0;37mPress [ENTER] to close terminal...\\033[0m'\n")
        f.write("read -r\n")
    
    os.chmod(script_path, 0o700) # Ensure it is only accessible and executable by the owner

    cmd = ["omarchy-launch-terminal", "bash", script_path]
    try:
        subprocess.Popen(cmd, start_new_session=True)
        print(json.dumps({"success": True}))
    except Exception:
        subprocess.Popen(["xdg-terminal-exec", "bash", script_path], start_new_session=True)
        print(json.dumps({"success": True}))

def main():
    parser = argparse.ArgumentParser(description="Agent Fixes & Shell Recipes helper")
    subparsers = parser.add_subparsers(dest="subcommand")

    p_list = subparsers.add_parser("list")
    
    p_add = subparsers.add_parser("add")
    p_add.add_argument("--title", required=True)
    p_add.add_argument("--category", default="General")
    p_add.add_argument("--tags", default="")
    p_add.add_argument("--description", default="")
    p_add.add_argument("--solution", default="")
    p_add.add_argument("--prompt", default="")

    p_del = subparsers.add_parser("delete")
    p_del.add_argument("--id", required=True)

    p_launch = subparsers.add_parser("launch")
    p_launch.add_argument("--id", required=True)
    p_launch.add_argument("--custom-note", default="")

    p_custom = subparsers.add_parser("launch-custom")
    p_custom.add_argument("--category", default="General")
    p_custom.add_argument("--tags", default="")
    p_custom.add_argument("--issue", required=True)
    p_custom.add_argument("--save", action="store_true")
    
    p_list_seq = subparsers.add_parser("list-seq")

    p_add_seq = subparsers.add_parser("add-seq")
    p_add_seq.add_argument("--title", required=True)
    p_add_seq.add_argument("--category", default="General")
    p_add_seq.add_argument("--tags", default="")
    p_add_seq.add_argument("--description", default="")
    p_add_seq.add_argument("--commands", required=True)

    p_del_seq = subparsers.add_parser("delete-seq")
    p_del_seq.add_argument("--id", required=True)

    p_run_seq = subparsers.add_parser("run-seq")
    p_run_seq.add_argument("--id", required=True)

    args = parser.parse_args()

    if args.subcommand == "list":
        cmd_list(args)
    elif args.subcommand == "add":
        cmd_add(args)
    elif args.subcommand == "delete":
        cmd_delete(args)
    elif args.subcommand == "launch":
        cmd_launch(args)
    elif args.subcommand == "launch-custom":
        cmd_launch_custom(args)
    elif args.subcommand == "list-seq":
        cmd_list_seq(args)
    elif args.subcommand == "add-seq":
        cmd_add_seq(args)
    elif args.subcommand == "delete-seq":
        cmd_del_seq(args)
    elif args.subcommand == "run-seq":
        cmd_run_seq(args)
    else:
        cmd_list(args)

if __name__ == "__main__":
    main()
