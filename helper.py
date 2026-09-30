#!/usr/bin/env python3
"""
Mahan Troubleshooter - Backend Helper & IPC Server
===================================================
All user-entered data (prompts, custom notes, titles, descriptions,
commands, tags, solutions) is treated as STRICTLY SENSITIVE.

Zero-Argv Architecture:
1. IPC Mode (Primary): QML connects to a private UNIX domain socket at
   $XDG_RUNTIME_DIR/omarchy/troubleshooter/ipc.sock (0700 dir, 0600 socket).
   Requests & responses are single-line JSON payloads over the stream.
   Zero process spawning occurs for IPC operations; nothing appears in
   ps/top/procfs.

2. Process Fallback Mode (CLI): If the socket is unreachable, QML spawns
   `helper.py <subcommand>` with `stdinEnabled: true`. The request payload
   is piped via process STDIN (never argv). Argv contains only the fixed
   subcommand name.

3. Agent Launch Staging: When an agent is triggered (opencode), the full
   assembled prompt is written to a private 0600 file inside the 0700 runtime
   directory. The launcher terminal is invoked with `opencode run -f <path>`
   passing a generic instruction message. The private prompt file is deleted
   immediately upon agent completion.
"""

import os
import sys
import json
import socket
import select
import subprocess
import time
import tempfile
import secrets
import stat

DATA_FILE = os.path.expanduser("~/.config/omarchy/troubleshooter-log.json")
SEQ_DATA_FILE = os.path.expanduser("~/.config/omarchy/troubleshooter-sequences.json")

AGENT_GENERIC_MESSAGE = (
    "Your complete task briefing is in the attached file. Read it fully first, "
    "then carry out every step autonomously without asking for confirmation."
)
AGENT_SESSION_TITLE = "Omarchy Troubleshooter"

def get_secure_runtime_dir():
    base_run = os.environ.get("XDG_RUNTIME_DIR")
    if base_run and os.path.isdir(base_run):
        secure_dir = os.path.join(base_run, "omarchy", "troubleshooter")
    else:
        secure_dir = os.path.expanduser("~/.local/state/omarchy/troubleshooter")
    os.makedirs(secure_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(secure_dir, 0o700)
    except OSError:
        pass
    return secure_dir

def get_socket_path():
    return os.path.join(get_secure_runtime_dir(), "ipc.sock")

def get_secure_temp_dir():
    recipes_dir = os.path.join(get_secure_runtime_dir(), "recipes")
    os.makedirs(recipes_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(recipes_dir, 0o700)
    except OSError:
        pass
    return recipes_dir

def get_secure_prompts_dir():
    prompts_dir = os.path.join(get_secure_runtime_dir(), "prompts")
    os.makedirs(prompts_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(prompts_dir, 0o700)
    except OSError:
        pass
    return prompts_dir

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

def _write_prompt_file(prompt_text):
    """Write the assembled prompt to a private 0600 file in the runtime dir."""
    prompts_dir = get_secure_prompts_dir()
    fd, path = tempfile.mkstemp(prefix="prompt-", suffix=".md", dir=prompts_dir, text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(prompt_text)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path

def run_agent_prompt(prompt_text):
    """
    Launch the agent via terminal, loading the full briefing from a private file.
    No prompt text or user notes appear in argv. The launcher script takes the
    prompt file path as $1 and removes it when the agent completes.
    """
    prompt_path = _write_prompt_file(prompt_text)
    token = secrets.token_hex(8)
    lines = [
        "#!/bin/bash",
        "set -euo pipefail",
        "trap 'rm -f \"$0\" \"${1:-}\"' EXIT",
        "clear",
        f"cat <<'BANNER_{token}'",
        "=====================================================",
        "  OMARCHY TROUBLESHOOTER - Agent Auto-Fix",
        "  Task briefing loaded securely from private file.",
        "=====================================================",
        f"BANNER_{token}",
        "",
        "if ! command -v opencode >/dev/null 2>&1; then",
        "  echo 'opencode is not installed. Choose an agent with: omarchy default agent <name>'",
        "  read -r -p 'Press [ENTER] to close terminal...'",
        "  exit 1",
        "fi",
        "",
        "status=0",
        f'opencode run --auto --title "{AGENT_SESSION_TITLE}" -f "$1" "{AGENT_GENERIC_MESSAGE}" || status=$?',
        'rm -f "$1"',
        'echo ""',
        'echo "Agent run completed (status $status)."',
        "read -r -p 'Press [ENTER] to close terminal...'",
    ]
    
    script_fd, script_path = tempfile.mkstemp(
        prefix="omarchy-agent-", suffix=".sh", dir=get_secure_temp_dir(), text=True
    )
    with os.fdopen(script_fd, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    os.chmod(script_path, 0o700)
    
    cmd = ["omarchy-launch-terminal", "bash", script_path, prompt_path]
    try:
        subprocess.Popen(cmd, start_new_session=True)
        return True
    except Exception:
        try:
            subprocess.Popen(["xdg-terminal-exec", "bash", script_path, prompt_path], start_new_session=True)
            return True
        except Exception:
            return False

def _unique_id(prefix):
    return f"{prefix}-{int(time.time())}-{secrets.token_hex(4)}"

# ============================================================================
# Core Business Logic Handlers
# All inputs are dictionaries parsed from JSON (from Socket or STDIN).
# ZERO arguments travel on the process command-line.
# ============================================================================

def handle_list(req):
    return {"success": True, "data": load_data()}

def handle_add(req):
    title = str(req.get("title", "")).strip()
    if not title:
        return {"success": False, "error": "Title is required"}
    data = load_data()
    raw_tags = req.get("tags", "")
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = []
    
    desc = str(req.get("description", ""))
    sol = str(req.get("solution", ""))
    p_custom = str(req.get("prompt", ""))
    default_p = f"Fix: {title}. Details: {desc}. Known solution: {sol}"
    
    item = {
        "id": _unique_id("issue"),
        "title": title,
        "category": str(req.get("category", "")).strip() or "General",
        "tags": tags,
        "description": desc,
        "solution": sol,
        "prompt": p_custom or default_p
    }
    data.insert(0, item)
    save_data(data)
    return {"success": True, "id": item["id"]}

def handle_delete(req):
    target_id = str(req.get("id", ""))
    if not target_id:
        return {"success": False, "error": "ID is required"}
    data = load_data()
    data = [x for x in data if x.get("id") != target_id]
    save_data(data)
    return {"success": True}

def handle_launch(req):
    target_id = str(req.get("id", ""))
    if not target_id:
        return {"success": False, "error": "ID is required"}
    data = load_data()
    target = next((x for x in data if x.get("id") == target_id), None)
    if not target:
        return {"success": False, "error": "Item not found"}
    
    custom_note = str(req.get("custom_note", "")).strip()
    parts = [
        "[CONTEXT / LOGGED ISSUE]",
        f"Title: {target.get('title', '')}",
        f"Category: {target.get('category', 'General')}",
        f"Tags: {', '.join(target.get('tags', []))}",
        f"Details: {target.get('solution', '')}"
    ]
    if custom_note:
        parts.extend(["", "[USER NOTE]", custom_note])
    parts.extend(["", "[INSTRUCTIONS]", target.get("prompt", "")])
    
    full_prompt = "\n".join(parts)
    run_agent_prompt(full_prompt)
    return {"success": True}

def handle_launch_custom(req):
    issue = str(req.get("issue", "")).strip()
    if not issue:
        return {"success": False, "error": "Issue description is required"}
    
    category = str(req.get("category", "")).strip() or "General"
    raw_tags = req.get("tags", "")
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = []
    
    full_prompt = (
        "[USER PC ISSUE REPORT]\n"
        f"Category: {category}\n"
        f"Tags: {', '.join(tags)}\n"
        f"Issue: {issue}\n\n"
        "Please diagnose the cause on this Omarchy Arch Linux system, "
        "check relevant logs and configs, and fix it properly."
    )
    
    if req.get("save", False):
        data = load_data()
        item = {
            "id": _unique_id("issue"),
            "title": issue[:50],
            "category": category,
            "tags": tags,
            "description": issue,
            "solution": "",
            "prompt": full_prompt
        }
        data.insert(0, item)
        save_data(data)
        
    run_agent_prompt(full_prompt)
    return {"success": True}

def handle_list_seq(req):
    return {"success": True, "data": load_seq_data()}

def handle_add_seq(req):
    title = str(req.get("title", "")).strip()
    commands = str(req.get("commands", "")).strip()
    if not title:
        return {"success": False, "error": "Title is required"}
    if not commands:
        return {"success": False, "error": "Commands are required"}
        
    raw_tags = req.get("tags", "")
    if isinstance(raw_tags, list):
        tags = [str(t).strip() for t in raw_tags if str(t).strip()]
    elif isinstance(raw_tags, str):
        tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    else:
        tags = []
        
    data = load_seq_data()
    item = {
        "id": _unique_id("seq"),
        "title": title,
        "category": str(req.get("category", "")).strip() or "General",
        "tags": tags,
        "description": str(req.get("description", "")),
        "commands": commands
    }
    data.insert(0, item)
    save_seq_data(data)
    return {"success": True, "id": item["id"]}

def handle_del_seq(req):
    target_id = str(req.get("id", ""))
    if not target_id:
        return {"success": False, "error": "ID is required"}
    data = load_seq_data()
    data = [x for x in data if x.get("id") != target_id]
    save_seq_data(data)
    return {"success": True}

def handle_run_seq(req):
    target_id = str(req.get("id", ""))
    if not target_id:
        return {"success": False, "error": "ID is required"}
    data = load_seq_data()
    target = next((x for x in data if x.get("id") == target_id), None)
    if not target:
        return {"success": False, "error": "Sequence not found"}
        
    secure_dir = get_secure_temp_dir()
    script_fd, script_path = tempfile.mkstemp(
        prefix="omarchy-recipe-", suffix=".sh", dir=secure_dir, text=True
    )
    
    blob = "\n".join([
        str(target.get("title", "")),
        str(target.get("category", "")),
        ",".join(target.get("tags", []) or []),
        str(target.get("commands", "")),
    ])
    token = secrets.token_hex(16)
    while f"HEADER_{token}" in blob:
        token = secrets.token_hex(16)
        
    cmd_lines = [l.strip() for l in target.get("commands", "").split("\n") if l.strip()]
    
    with os.fdopen(script_fd, "w", encoding="utf-8") as f:
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
            while f"STEP_{step_token}" in line:
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
    return {"success": True}

DISPATCH = {
    "list": handle_list,
    "add": handle_add,
    "delete": handle_delete,
    "launch": handle_launch,
    "launch-custom": handle_launch_custom,
    "list-seq": handle_list_seq,
    "add-seq": handle_add_seq,
    "delete-seq": handle_del_seq,
    "run-seq": handle_run_seq,
}

def process_request(action, payload):
    handler = DISPATCH.get(action)
    if not handler:
        return {"success": False, "error": f"Unknown action: {action}"}
    try:
        return handler(payload)
    except Exception as e:
        return {"success": False, "error": str(e)}

# ============================================================================
# Server & Fallback Execution Modes
# ============================================================================

def run_server():
    """
    Run an in-memory UNIX socket server for the active user session.
    Sockets are created inside $XDG_RUNTIME_DIR/omarchy/troubleshooter/ with 0600
    permissions so only the current user can communicate with it.
    """
    sock_path = get_socket_path()
    if os.path.exists(sock_path):
        # Check if already alive
        test_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            test_sock.connect(sock_path)
            test_sock.sendall(b'{"action":"ping"}\n')
            resp = test_sock.recv(1024)
            if resp:
                print(f"Troubleshooter server already running at {sock_path}")
                return
        except Exception:
            try:
                os.unlink(sock_path)
            except OSError:
                pass
        finally:
            test_sock.close()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(sock_path)
    os.chmod(sock_path, 0o600)
    server.listen(16)
    server.setblocking(False)
    
    print(f"Troubleshooter IPC server active: {sock_path}")
    inputs = [server]
    
    try:
        while True:
            readable, _, _ = select.select(inputs, [], [], 1.0)
            for s in readable:
                if s is server:
                    conn, _ = server.accept()
                    conn.setblocking(False)
                    inputs.append(conn)
                else:
                    try:
                        data = s.recv(65536)
                        if data:
                            lines = data.decode("utf-8", errors="replace").split("\n")
                            for line in lines:
                                line = line.strip()
                                if not line:
                                    continue
                                try:
                                    req = json.loads(line)
                                    action = req.get("action", "")
                                    if action == "ping":
                                        resp = {"success": True, "pong": True}
                                    else:
                                        resp = process_request(action, req.get("payload", {}))
                                except Exception as e:
                                    resp = {"success": False, "error": f"Malformed request: {str(e)}"}
                                s.sendall(json.dumps(resp).encode("utf-8") + b"\n")
                        else:
                            inputs.remove(s)
                            s.close()
                    except Exception:
                        if s in inputs:
                            inputs.remove(s)
                        try:
                            s.close()
                        except Exception:
                            pass
    finally:
        try:
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)
        except Exception:
            pass

def run_cli_fallback(action):
    """
    Fallback execution when invoked directly as a process.
    Reads the JSON payload strictly from STDIN.
    Zero user data arrives via argv.
    """
    raw_input = sys.stdin.read()
    payload = {}
    if raw_input.strip():
        try:
            payload = json.loads(raw_input)
        except Exception as e:
            print(json.dumps({"success": False, "error": f"Invalid JSON on STDIN: {str(e)}"}))
            return
            
    result = process_request(action, payload)
    print(json.dumps(result))

def main():
    if len(sys.argv) < 2:
        print("Usage: helper.py <server|action_name>")
        print("Actions: " + ", ".join(DISPATCH.keys()))
        sys.exit(1)
        
    cmd = sys.argv[1]
    if cmd in ("server", "--server", "-s"):
        run_server()
    elif cmd in DISPATCH:
        run_cli_fallback(cmd)
    else:
        print(json.dumps({"success": False, "error": f"Unknown command: {cmd}"}))
        sys.exit(1)

if __name__ == "__main__":
    main()
