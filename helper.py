#!/usr/bin/env python3
import os
import json
import argparse
import subprocess
import time
import tempfile
import secrets

DATA_FILE = os.path.expanduser("~/.config/omarchy/troubleshooter-log.json")
SEQ_DATA_FILE = os.path.expanduser("~/.config/omarchy/troubleshooter-sequences.json")

def get_secure_temp_dir():
    base_run = os.environ.get("XDG_RUNTIME_DIR")
    if base_run and os.path.isdir(base_run):
        secure_dir = os.path.join(base_run, "omarchy", "troubleshooter", "recipes")
    else:
        secure_dir = os.path.expanduser("~/.local/state/omarchy/troubleshooter/recipes")
    os.makedirs(secure_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(secure_dir, 0o700)
    except OSError:
        pass
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

def _unique_id(prefix):
    # time + cryptographic randomness: no collisions even on rapid successive adds
    return f"{prefix}-{int(time.time())}-{secrets.token_hex(4)}"

def cmd_list(args):
    data = load_data()
    print(json.dumps(data))

def cmd_add(args):
    data = load_data()
    item = {
        "id": _unique_id("issue"),
        "title": args.title,
        "category": args.category or "General",
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else [],
        "description": args.description or "",
        "solution": args.solution or "",
        "prompt": args.prompt or f"Fix: {args.title}. Details: {args.description}. Known solution: {args.solution}"
    }
    data.insert(0, item)
    save_data(data)
    print(json.dumps({"success": True, "id": item["id"]}))

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
    full_prompt = (f"[CONTEXT]\nTitle: {target.get('title')}\nDetails: {target.get('solution')}\n\n[NOTE]\n{args.custom_note}\n\n" if args.custom_note else "") + target.get('prompt', "")
    run_agent_prompt(full_prompt)
    print(json.dumps({"success": True}))

def cmd_launch_custom(args):
    # Quick-report path used by the panel's fast issue box. All user input travels
    # exclusively through subprocess argv (never a shell string), so metacharacters
    # in --issue/--category/--tags are inert data.
    full_prompt = (
        "[USER PC ISSUE REPORT]\nCategory: " + (args.category or "General") + "\n"
        "Tags: " + (args.tags or "") + "\nIssue: " + args.issue + "\n\n"
        "Please diagnose the cause on this Omarchy Arch Linux system, "
        "check relevant logs and configs, and fix it properly."
    )
    if args.save:
        data = load_data()
        item = {
            "id": _unique_id("issue"),
            "title": args.issue[:50],
            "category": args.category or "General",
            "tags": [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else [],
            "description": args.issue,
            "solution": "",
            "prompt": full_prompt
        }
        data.insert(0, item)
        save_data(data)
    run_agent_prompt(full_prompt)
    print(json.dumps({"success": True}))

def cmd_list_seq(args):
    print(json.dumps(load_seq_data()))

def cmd_add_seq(args):
    data = load_seq_data()
    item = {
        "id": _unique_id("seq"),
        "title": args.title,
        "category": args.category or "General",
        "tags": [t.strip() for t in args.tags.split(",") if t.strip()] if args.tags else [],
        "description": args.description or "",
        "commands": args.commands or "echo 'No commands configured'"
    }
    data.insert(0, item)
    save_seq_data(data)
    print(json.dumps({"success": True, "id": item["id"]}))

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

    secure_dir = get_secure_temp_dir()
    script_fd, script_path = tempfile.mkstemp(prefix="omarchy-recipe-", suffix=".sh", dir=secure_dir, text=True)

    # Heredoc delimiters are cryptographic nonces AND verified absent from every
    # user-controlled byte below, so even a deliberately crafted title/commands
    # payload containing "HEADER_<guess>" can never terminate a heredoc early.
    blob = "\n".join([
        str(target.get("title", "")),
        str(target.get("category", "")),
        ",".join(target.get("tags", []) or []),
        str(target.get("commands", "")),
    ])
    token = secrets.token_hex(16)
    while ("HEADER_" + token) in blob:
        token = secrets.token_hex(16)
    
    cmd_lines = [l.strip() for l in target.get("commands", "").split("\n") if l.strip()]

    with os.fdopen(script_fd, 'w', encoding='utf-8') as f:
        f.write("#!/bin/bash\nset -euo pipefail\ntrap 'rm -f \"$0\"' EXIT\nclear\n")
        f.write(f"cat <<'HEADER_{token}'\n")
        f.write("=====================================================\n")
        f.write(f"  SHELL RECIPE: {target.get('title', 'Recipe')}\n")
        f.write(f"  Category: {target.get('category', 'General')}  |  Tags: {', '.join(target.get('tags', []))}\n")
        f.write("=====================================================\n\n")
        f.write("Commands to execute:\n")
        for idx, line in enumerate(cmd_lines, 1):
            f.write(f"  {idx}. {line}\n")
        f.write("-----------------------------------------------------\n")
        f.write(f"HEADER_{token}\n\n")
        
        f.write("echo -e '\\033[1;32mPress [ENTER] to execute, or Ctrl+C to cancel...\\033[0m'\n")
        f.write("read -r\n\n")
        
        for idx, line in enumerate(cmd_lines, 1):
            if line.startswith("#"):
                f.write(f"{line}\n")
                continue
            step_token = secrets.token_hex(16)
            while ("STEP_" + step_token) in line:
                step_token = secrets.token_hex(16)
            f.write(f"echo -e '\\n\\033[1;35m>> [{idx}/{len(cmd_lines)}] Running:\\033[0m'\n")
            f.write(f"cat <<'STEP_{step_token}'\n$ {line}\nSTEP_{step_token}\n")
            f.write(f"{line}\n")
            f.write("echo -e '\\033[0;32m   ✓ Step finished.\\033[0m'\n")
        
        f.write("\necho -e '\\n\\033[1;32m=====================================================\\033[0m'\n")
        f.write("echo -e '\\033[1;32m  ✓ All recipe commands completed.\\033[0m'\n")
        f.write("echo -e '\\033[1;32m=====================================================\\033[0m'\n")
        f.write("echo -e '\\033[0;37mPress [ENTER] to close terminal...\\033[0m'\n")
        f.write("read -r\n")
    
    os.chmod(script_path, 0o700)
    subprocess.Popen(["omarchy-launch-terminal", "bash", script_path], start_new_session=True)
    print(json.dumps({"success": True}))

def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="subcommand")
    
    subparsers.add_parser("list")
    p_add = subparsers.add_parser("add")
    p_add.add_argument("--title", required=True); p_add.add_argument("--category"); p_add.add_argument("--tags"); p_add.add_argument("--description"); p_add.add_argument("--solution"); p_add.add_argument("--prompt")
    p_del = subparsers.add_parser("delete"); p_del.add_argument("--id", required=True)
    p_launch = subparsers.add_parser("launch"); p_launch.add_argument("--id", required=True); p_launch.add_argument("--custom-note")
    p_custom = subparsers.add_parser("launch-custom")
    p_custom.add_argument("--issue", required=True); p_custom.add_argument("--category", default="General"); p_custom.add_argument("--tags", default=""); p_custom.add_argument("--save", action="store_true")
    
    subparsers.add_parser("list-seq")
    p_add_seq = subparsers.add_parser("add-seq")
    p_add_seq.add_argument("--title", required=True); p_add_seq.add_argument("--category"); p_add_seq.add_argument("--tags"); p_add_seq.add_argument("--description"); p_add_seq.add_argument("--commands", required=True)
    p_del_seq = subparsers.add_parser("delete-seq"); p_del_seq.add_argument("--id", required=True)
    p_run_seq = subparsers.add_parser("run-seq"); p_run_seq.add_argument("--id", required=True)

    args = parser.parse_args()
    cmds = {"list": cmd_list, "add": cmd_add, "delete": cmd_delete, "launch": cmd_launch, "launch-custom": cmd_launch_custom, "list-seq": cmd_list_seq, "add-seq": cmd_add_seq, "delete-seq": cmd_del_seq, "run-seq": cmd_run_seq}
    (cmds.get(args.subcommand, cmd_list))(args)

if __name__ == "__main__":
    main()
