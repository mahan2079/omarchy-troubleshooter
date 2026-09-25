import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "mahan.troubleshooter"
  ipcTarget: "mahan.troubleshooter"
  manageIpc: false

  readonly property string helperCmd: Qt.resolvedUrl("helper.py").toString().replace(/^file:\/\//, "")
  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color accent: bar ? Color.accent : Color.accent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family

  property int activeTab: 0 // 0 = Agent Fixes, 1 = Shell Recipes

  // ---------- Data Models with Defaults ----------

  property var allIssues: [
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

  property var allSequences: [
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

  property string activeAgentName: "Agent"
  property string searchQuery: ""
  property string selectedCategory: "ALL"

  // Quick Issue
  property string quickIssueText: ""
  property string quickCategory: "General"
  property bool quickSave: true

  // Form states
  property bool showAddForm: false
  property string formTitle: ""
  property string formCategory: "General"
  property string formTags: ""
  property string formDescription: ""
  property string formSolution: ""
  property string formPrompt: ""
  property string formCommands: ""

  property string statusMessage: ""

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  // ---------- Reactive Filtered Properties ----------

  readonly property var filteredIssues: {
    var list = root.allIssues || []
    var q = String(root.searchQuery || "").toLowerCase().trim()
    var cat = String(root.selectedCategory || "ALL").toUpperCase()
    var out = []

    for (var i = 0; i < list.length; i++) {
      var item = list[i]
      if (!item) continue
      var itemCat = String(item.category || "General").toUpperCase()
      if (cat !== "ALL" && itemCat !== cat) continue

      if (q !== "") {
        var t = String(item.title || "").toLowerCase()
        var d = String(item.description || "").toLowerCase()
        var s = String(item.solution || "").toLowerCase()
        var tags = Array.isArray(item.tags) ? item.tags.join(" ").toLowerCase() : ""
        if (t.indexOf(q) === -1 && d.indexOf(q) === -1 && s.indexOf(q) === -1 && tags.indexOf(q) === -1 && itemCat.toLowerCase().indexOf(q) === -1) {
          continue
        }
      }
      out.push(item)
    }
    return out
  }

  readonly property var filteredSequences: {
    var list = root.allSequences || []
    var q = String(root.searchQuery || "").toLowerCase().trim()
    var cat = String(root.selectedCategory || "ALL").toUpperCase()
    var out = []

    for (var i = 0; i < list.length; i++) {
      var item = list[i]
      if (!item) continue
      var itemCat = String(item.category || "General").toUpperCase()
      if (cat !== "ALL" && itemCat !== cat) continue

      if (q !== "") {
        var t = String(item.title || "").toLowerCase()
        var d = String(item.description || "").toLowerCase()
        var c = String(item.commands || "").toLowerCase()
        var tags = Array.isArray(item.tags) ? item.tags.join(" ").toLowerCase() : ""
        if (t.indexOf(q) === -1 && d.indexOf(q) === -1 && c.indexOf(q) === -1 && tags.indexOf(q) === -1 && itemCat.toLowerCase().indexOf(q) === -1) {
          continue
        }
      }
      out.push(item)
    }
    return out
  }

  // ---------- Live FileView Monitoring ----------

  FileView {
    id: jsonFile
    path: Quickshell.env("HOME") + "/.config/omarchy/troubleshooter-log.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try {
        var arr = JSON.parse(text() || "[]")
        if (Array.isArray(arr) && arr.length > 0) root.allIssues = arr
      } catch (e) {}
    }
  }

  FileView {
    id: seqJsonFile
    path: Quickshell.env("HOME") + "/.config/omarchy/troubleshooter-sequences.json"
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: {
      try {
        var arr = JSON.parse(text() || "[]")
        if (Array.isArray(arr) && arr.length > 0) root.allSequences = arr
      } catch (e) {}
    }
  }

  // ---------- Background Refresh & Watch ----------

  Process {
    id: agentProc
    command: ["omarchy-default-agent"]
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        var name = String(text || "").trim()
        if (name !== "") root.activeAgentName = name
      }
    }
  }

  function refreshList() {
    jsonFile.reload()
    seqJsonFile.reload()
    if (!agentProc.running) agentProc.running = true
  }

  // ---------- Detached Action Handlers ----------

  function launchIssue(issueId, customNote) {
    var cmd = [root.helperCmd, "launch", "--id", issueId]
    if (customNote && customNote.trim() !== "") {
      cmd.push("--custom-note")
      cmd.push(customNote.trim())
    }
    Quickshell.execDetached(cmd)
    root.close()
  }

  function deleteIssue(issueId) {
    Quickshell.execDetached([root.helperCmd, "delete", "--id", issueId])
    refreshTimer.restart()
  }

  function launchQuickIssue() {
    if (!quickIssueText.trim()) return
    var cmd = [root.helperCmd, "launch-custom", "--issue", quickIssueText.trim(), "--category", quickCategory]
    if (quickSave) cmd.push("--save")
    Quickshell.execDetached(cmd)
    quickIssueText = ""
    root.close()
  }

  function runSequence(seqId) {
    Quickshell.execDetached([root.helperCmd, "run-seq", "--id", seqId])
    root.close()
  }

  function deleteSequence(seqId) {
    Quickshell.execDetached([root.helperCmd, "delete-seq", "--id", seqId])
    refreshTimer.restart()
  }

  function saveNewIssue() {
    if (!formTitle.trim()) return
    var cmd = [
      root.helperCmd, "add",
      "--title", formTitle.trim(),
      "--category", formCategory.trim() || "General",
      "--tags", formTags.trim(),
      "--description", formDescription.trim(),
      "--solution", formSolution.trim(),
      "--prompt", formPrompt.trim()
    ]
    Quickshell.execDetached(cmd)
    formTitle = ""
    formTags = ""
    formDescription = ""
    formSolution = ""
    formPrompt = ""
    showAddForm = false
    refreshTimer.restart()
  }

  function saveNewSequence() {
    if (!formTitle.trim()) return
    var cmd = [
      root.helperCmd, "add-seq",
      "--title", formTitle.trim(),
      "--category", formCategory.trim() || "General",
      "--tags", formTags.trim(),
      "--description", formDescription.trim(),
      "--commands", formCommands.trim()
    ]
    Quickshell.execDetached(cmd)
    formTitle = ""
    formTags = ""
    formDescription = ""
    formCommands = ""
    showAddForm = false
    refreshTimer.restart()
  }

  Timer {
    id: refreshTimer
    interval: 250
    repeat: false
    onTriggered: root.refreshList()
  }

  IpcHandler {
    target: "mahan.troubleshooter"
    function open() { root.open() }
    function close() { root.close() }
    function toggle() { root.toggle() }
    function refresh() { root.refreshList() }
  }

  Component.onCompleted: refreshList()
  onOpenedChanged: if (opened) {
    refreshList()
    root.statusMessage = ""
  }

  // ---------- Bar Icon Button ----------

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf0ad"
    tooltipText: "Troubleshooter: Agent Fixes & Shell Recipes"
    active: root.opened
    onPressed: function(buttonCode) {
      if (buttonCode === Qt.MiddleButton) root.refreshList()
      else root.toggle()
    }
  }

  // ---------- Dropdown / Popup Panel ----------

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(480))
    contentHeight: panel.fittedContentHeight(mainColumn.implicitHeight, Style.space(640))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }

      Flickable {
        id: flickable
        anchors.fill: parent
        contentWidth: width
        contentHeight: mainColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        Column {
          id: mainColumn
          width: flickable.width
          spacing: Style.space(12)

          // ---------- Hero ----------
          PanelHero {
            width: parent.width
            title: "Troubleshooter"
            meta: root.activeTab === 0 ? ("Agent: " + root.activeAgentName) : "Managed Shell Tasks"
            foreground: root.foreground
            fontFamily: root.fontFamily
            trailingControl: Component {
              Button {
                text: root.showAddForm ? "✕ Close" : (root.activeTab === 0 ? "＋ Log Issue" : "＋ Add Recipe")
                fontSize: Style.font.caption
                foreground: root.accent
                fontFamily: root.fontFamily
                bordered: true
                onClicked: root.showAddForm = !root.showAddForm
              }
            }
          }

          // ---------- Side-by-Side Tab Switcher ----------
          Row {
            width: parent.width
            spacing: Style.space(8)

            Button {
              width: (parent.width - Style.space(8)) / 2
              text: "󱚣 Agent Fixes"
              fontSize: Style.font.bodySmall
              selected: root.activeTab === 0
              bordered: true
              foreground: root.foreground
              onClicked: {
                root.activeTab = 0
                root.showAddForm = false
              }
            }

            Button {
              width: (parent.width - Style.space(8)) / 2
              text: "󰆍 Shell Recipes"
              fontSize: Style.font.bodySmall
              selected: root.activeTab === 1
              bordered: true
              foreground: root.foreground
              onClicked: {
                root.activeTab = 1
                root.showAddForm = false
              }
            }
          }

          // =========================================================================
          // TAB 0: AGENT FIXES
          // =========================================================================
          Column {
            visible: root.activeTab === 0
            width: parent.width
            spacing: Style.space(12)

            // ---------- Quick Fix / Instant Issue Prompt ----------
            BorderSurface {
              width: parent.width
              implicitHeight: quickRunCol.implicitHeight + Style.space(20)
              color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.04)
              radius: Style.cornerRadius
              borderSpec: Border.controlSpec("normal", root.foreground, root.accent)

              Column {
                id: quickRunCol
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.margins: Style.space(10)
                spacing: Style.space(8)

                PanelSectionHeader {
                  text: "⚡ QUICK FIX WITH " + root.activeAgentName.toUpperCase()
                  foreground: root.accent
                  fontFamily: root.fontFamily
                }

                Text {
                  text: "Describe problem to combine with system context and prompt agent:"
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                  width: parent.width
                }

                TextField {
                  id: quickInput
                  width: parent.width
                  placeholderText: "e.g. bluetooth audio disconnected / mic volume muted..."
                  text: root.quickIssueText
                  font.pixelSize: Style.font.bodySmall
                  onTextChanged: root.quickIssueText = text
                  onAccepted: root.launchQuickIssue()
                }

                Row {
                  width: parent.width
                  spacing: Style.space(8)

                  Button {
                    text: "Fix with " + root.activeAgentName
                    iconText: "⚡"
                    fontSize: Style.font.bodySmall
                    foreground: root.foreground
                    accent: root.accent
                    selected: true
                    bordered: true
                    onClicked: root.launchQuickIssue()
                  }

                  Button {
                    text: root.quickSave ? "✓ Auto-Save to Memory" : "Don't Save"
                    fontSize: Style.font.caption
                    foreground: root.quickSave ? root.accent : root.dim
                    bordered: true
                    onClicked: root.quickSave = !root.quickSave
                  }
                }
              }
            }

            // ---------- Add New Issue Form (Collapsible) ----------
            Column {
              visible: root.showAddForm
              width: parent.width
              spacing: Style.space(8)

              PanelSeparator { foreground: root.foreground }

              PanelSectionHeader {
                text: "LOG NEW RECURRING PROBLEM"
                foreground: root.accent
                fontFamily: root.fontFamily
              }

              Text {
                text: "Title / Error Name:"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              TextField {
                width: parent.width
                placeholderText: "e.g. WiFi Drop after Suspend"
                text: root.formTitle
                onTextChanged: root.formTitle = text
              }

              Row {
                width: parent.width
                spacing: Style.space(8)

                Column {
                  width: (parent.width - Style.space(8)) / 2
                  spacing: Style.space(4)
                  Text { text: "Category:"; color: root.dim; font.pixelSize: Style.font.caption }
                  TextField {
                    width: parent.width
                    placeholderText: "Audio / Display / Network..."
                    text: root.formCategory
                    onTextChanged: root.formCategory = text
                  }
                }

                Column {
                  width: (parent.width - Style.space(8)) / 2
                  spacing: Style.space(4)
                  Text { text: "Tags (comma separated):"; color: root.dim; font.pixelSize: Style.font.caption }
                  TextField {
                    width: parent.width
                    placeholderText: "wifi, network, sleep"
                    text: root.formTags
                    onTextChanged: root.formTags = text
                  }
                }
              }

              Text {
                text: "Symptom / Description:"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              TextField {
                width: parent.width
                placeholderText: "What happens when this breaks?"
                text: root.formDescription
                onTextChanged: root.formDescription = text
              }

              Text {
                text: "Known Fix / Steps to resolve:"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              TextField {
                width: parent.width
                placeholderText: "e.g. restart iwd and reload module iwlwifi"
                text: root.formSolution
                onTextChanged: root.formSolution = text
              }

              Text {
                text: "Prompt Instructions for Agent (optional):"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              TextField {
                width: parent.width
                placeholderText: "Leave blank to auto-generate standard troubleshooting prompt"
                text: root.formPrompt
                onTextChanged: root.formPrompt = text
              }

              Button {
                width: parent.width
                text: "Save Issue to Memory"
                selected: true
                bordered: true
                foreground: root.foreground
                onClicked: root.saveNewIssue()
              }
            }

            // ---------- Category Filter & Search ----------
            PanelSeparator { foreground: root.foreground }

            Row {
              width: parent.width
              spacing: Style.space(6)

              TextField {
                width: parent.width - Style.space(80)
                placeholderText: "🔍 Filter issues or tags..."
                text: root.searchQuery
                font.pixelSize: Style.font.bodySmall
                onTextChanged: root.searchQuery = text
              }

              Button {
                width: Style.space(74)
                text: "Clear"
                fontSize: Style.font.caption
                foreground: root.dim
                bordered: true
                onClicked: {
                  root.searchQuery = ""
                  root.selectedCategory = "ALL"
                }
              }
            }

            // Category Pills
            Flickable {
              width: parent.width
              implicitHeight: categoryRow.implicitHeight + Style.space(4)
              contentWidth: categoryRow.implicitWidth
              flickableDirection: Flickable.HorizontalFlick
              boundsBehavior: Flickable.StopAtBounds
              clip: true

              Row {
                id: categoryRow
                spacing: Style.space(6)

                Repeater {
                  model: ["ALL", "AUDIO", "DISPLAY", "BLUETOOTH", "SHELL", "PACKAGES", "GENERAL"]
                  Button {
                    required property string modelData
                    text: modelData
                    fontSize: Style.font.caption
                    selected: root.selectedCategory === modelData
                    bordered: true
                    foreground: root.foreground
                    onClicked: root.selectedCategory = modelData
                  }
                }
              }
            }

            // ---------- List of Logged Issues ----------
            PanelSectionHeader {
              text: "KNOWN ISSUES & PRESETS (" + root.filteredIssues.length + ")"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Text {
              visible: root.filteredIssues.length === 0
              text: "No issues match your filter.\nClick '+ Log Issue' above to add one."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              horizontalAlignment: Text.AlignHCenter
              width: parent.width
              topPadding: Style.space(16)
              bottomPadding: Style.space(16)
            }

            Repeater {
              model: root.filteredIssues

              BorderSurface {
                id: issueCard
                required property var modelData
                required property int index

                property bool isExpanded: false
                property string customNoteText: ""

                width: mainColumn.width
                implicitHeight: cardContentCol.implicitHeight + Style.space(20)
                color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.04)
                radius: Style.cornerRadius
                borderSpec: Border.controlSpec("normal", root.foreground, root.accent)

                Column {
                  id: cardContentCol
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.top: parent.top
                  anchors.margins: Style.space(10)
                  spacing: Style.space(6)

                  // Title & Category Badge
                  Item {
                    width: parent.width
                    implicitHeight: Math.max(cardTitle.implicitHeight, catBadge.implicitHeight)

                    Text {
                      id: cardTitle
                      text: issueCard.modelData ? (issueCard.modelData.title || "Untitled") : ""
                      color: root.foreground
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.body
                      font.bold: true
                      elide: Text.ElideRight
                      anchors.left: parent.left
                      anchors.right: catBadge.left
                      anchors.rightMargin: Style.space(8)
                      anchors.verticalCenter: parent.verticalCenter
                    }

                    Rectangle {
                      id: catBadge
                      height: Style.space(20)
                      width: catText.implicitWidth + Style.space(12)
                      radius: height / 2
                      color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.20)
                      anchors.right: parent.right
                      anchors.verticalCenter: parent.verticalCenter

                      Text {
                        id: catText
                        anchors.centerIn: parent
                        text: issueCard.modelData ? (issueCard.modelData.category || "General") : ""
                        color: root.accent
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        font.bold: true
                      }
                    }
                  }

                  // Tags
                  Text {
                    visible: issueCard.modelData && Array.isArray(issueCard.modelData.tags) && issueCard.modelData.tags.length > 0
                    text: issueCard.modelData && Array.isArray(issueCard.modelData.tags) ? issueCard.modelData.tags.map(function(t) { return "#" + t }).join(" ") : ""
                    color: root.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }

                  // Description (Truncated unless expanded)
                  Text {
                    visible: issueCard.modelData && !!issueCard.modelData.description
                    text: issueCard.modelData ? (issueCard.modelData.description || "") : ""
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                    width: parent.width
                    maximumLineCount: issueCard.isExpanded ? 100 : 2
                    elide: Text.ElideRight
                  }

                  // Solution Preview (Truncated unless expanded)
                  Text {
                    visible: issueCard.modelData && !!issueCard.modelData.solution
                    text: issueCard.modelData ? ("💡 " + (issueCard.modelData.solution || "")) : ""
                    color: root.foreground
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    wrapMode: Text.WordWrap
                    width: parent.width
                    maximumLineCount: issueCard.isExpanded ? 100 : 1
                    elide: Text.ElideRight
                  }

                  // Show More / Show Less Toggle
                  Text {
                    text: issueCard.isExpanded ? "▲ Show less" : "▼ Show more & details"
                    color: root.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.bold: true

                    MouseArea {
                      anchors.fill: parent
                      cursorShape: Qt.PointingHandCursor
                      onClicked: issueCard.isExpanded = !issueCard.isExpanded
                    }
                  }

                  // Optional extra note input for this launch (shown when expanded)
                  TextField {
                    visible: issueCard.isExpanded
                    width: parent.width
                    placeholderText: "Extra note / symptom for this run (optional)..."
                    font.pixelSize: Style.font.caption
                    onTextChanged: issueCard.customNoteText = text
                    onAccepted: if (issueCard.modelData) root.launchIssue(issueCard.modelData.id, issueCard.customNoteText)
                  }

                  // Actions: Fix button & Delete button
                  Row {
                    width: parent.width
                    spacing: Style.space(8)

                    Button {
                      text: "⚡ Fix with " + root.activeAgentName
                      fontSize: Style.font.bodySmall
                      foreground: root.foreground
                      accent: root.accent
                      selected: true
                      bordered: true
                      width: parent.width - Style.space(40)
                      onClicked: if (issueCard.modelData) root.launchIssue(issueCard.modelData.id, issueCard.customNoteText)
                    }

                    Button {
                      text: "🗑"
                      fontSize: Style.font.bodySmall
                      foreground: bar ? bar.urgent : Color.urgent
                      bordered: true
                      width: Style.space(32)
                      tooltipText: "Delete from issue memory"
                      onClicked: if (issueCard.modelData) root.deleteIssue(issueCard.modelData.id)
                    }
                  }
                }
              }
            }
          }

          // =========================================================================
          // TAB 1: SHELL RECIPES
          // =========================================================================
          Column {
            visible: root.activeTab === 1
            width: parent.width
            spacing: Style.space(12)

            // ---------- Add New Sequence Form (Collapsible) ----------
            Column {
              visible: root.showAddForm
              width: parent.width
              spacing: Style.space(8)

              PanelSeparator { foreground: root.foreground }

              PanelSectionHeader {
                text: "CREATE NEW SHELL TASK RECIPE"
                foreground: root.accent
                fontFamily: root.fontFamily
              }

              Text {
                text: "Task Title / Name:"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              TextField {
                width: parent.width
                placeholderText: "e.g. Restart WirePlumber & Audio"
                text: root.formTitle
                onTextChanged: root.formTitle = text
              }

              Row {
                width: parent.width
                spacing: Style.space(8)

                Column {
                  width: (parent.width - Style.space(8)) / 2
                  spacing: Style.space(4)
                  Text { text: "Category:"; color: root.dim; font.pixelSize: Style.font.caption }
                  TextField {
                    width: parent.width
                    placeholderText: "Audio / Bluetooth / Network..."
                    text: root.formCategory
                    onTextChanged: root.formCategory = text
                  }
                }

                Column {
                  width: (parent.width - Style.space(8)) / 2
                  spacing: Style.space(4)
                  Text { text: "Tags (comma separated):"; color: root.dim; font.pixelSize: Style.font.caption }
                  TextField {
                    width: parent.width
                    placeholderText: "pipewire, reset"
                    text: root.formTags
                    onTextChanged: root.formTags = text
                  }
                }
              }

              Text {
                text: "Description / Purpose:"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              TextField {
                width: parent.width
                placeholderText: "What does this recipe do?"
                text: root.formDescription
                onTextChanged: root.formDescription = text
              }

              Text {
                text: "Commands to Run (in order, one per line):"
                color: root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
              TextField {
                width: parent.width
                placeholderText: "systemctl --user restart pipewire\nsleep 1\nwpctl status"
                text: root.formCommands
                onTextChanged: root.formCommands = text
              }

              Button {
                width: parent.width
                text: "Save Shell Recipe"
                selected: true
                bordered: true
                foreground: root.foreground
                onClicked: root.saveNewSequence()
              }
            }

            // ---------- Category Filter & Search ----------
            PanelSeparator { foreground: root.foreground }

            Row {
              width: parent.width
              spacing: Style.space(6)

              TextField {
                width: parent.width - Style.space(80)
                placeholderText: "🔍 Filter shell recipes or tags..."
                text: root.searchQuery
                font.pixelSize: Style.font.bodySmall
                onTextChanged: root.searchQuery = text
              }

              Button {
                width: Style.space(74)
                text: "Clear"
                fontSize: Style.font.caption
                foreground: root.dim
                bordered: true
                onClicked: {
                  root.searchQuery = ""
                  root.selectedCategory = "ALL"
                }
              }
            }

            // Category Pills for Sequences
            Flickable {
              width: parent.width
              implicitHeight: seqCategoryRow.implicitHeight + Style.space(4)
              contentWidth: seqCategoryRow.implicitWidth
              flickableDirection: Flickable.HorizontalFlick
              boundsBehavior: Flickable.StopAtBounds
              clip: true

              Row {
                id: seqCategoryRow
                spacing: Style.space(6)

                Repeater {
                  model: ["ALL", "MAINTENANCE", "AUDIO", "BLUETOOTH", "DISPLAY", "NETWORK", "GENERAL"]
                  Button {
                    required property string modelData
                    text: modelData
                    fontSize: Style.font.caption
                    selected: root.selectedCategory === modelData
                    bordered: true
                    foreground: root.foreground
                    onClicked: root.selectedCategory = modelData
                  }
                }
              }
            }

            // ---------- List of Shell Sequences ----------
            PanelSectionHeader {
              text: "SAVED SHELL RECIPES (" + root.filteredSequences.length + ")"
              foreground: root.foreground
              fontFamily: root.fontFamily
            }

            Text {
              visible: root.filteredSequences.length === 0
              text: "No recipes match your filter.\nClick '+ Add Recipe' above to create one."
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.bodySmall
              horizontalAlignment: Text.AlignHCenter
              width: parent.width
              topPadding: Style.space(16)
              bottomPadding: Style.space(16)
            }

            Repeater {
              model: root.filteredSequences

              BorderSurface {
                id: seqCard
                required property var modelData
                required property int index

                property bool isExpanded: false

                width: mainColumn.width
                implicitHeight: seqContentCol.implicitHeight + Style.space(20)
                color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.04)
                radius: Style.cornerRadius
                borderSpec: Border.controlSpec("normal", root.foreground, root.accent)

                Column {
                  id: seqContentCol
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.top: parent.top
                  anchors.margins: Style.space(10)
                  spacing: Style.space(6)

                  // Title & Category Badge
                  Item {
                    width: parent.width
                    implicitHeight: Math.max(seqTitle.implicitHeight, seqCatBadge.implicitHeight)

                    Text {
                      id: seqTitle
                      text: seqCard.modelData ? (seqCard.modelData.title || "Untitled Sequence") : ""
                      color: root.foreground
                      font.family: root.fontFamily
                      font.pixelSize: Style.font.body
                      font.bold: true
                      elide: Text.ElideRight
                      anchors.left: parent.left
                      anchors.right: seqCatBadge.left
                      anchors.rightMargin: Style.space(8)
                      anchors.verticalCenter: parent.verticalCenter
                    }

                    Rectangle {
                      id: seqCatBadge
                      height: Style.space(20)
                      width: seqCatText.implicitWidth + Style.space(12)
                      radius: height / 2
                      color: Qt.rgba(root.accent.r, root.accent.g, root.accent.b, 0.20)
                      anchors.right: parent.right
                      anchors.verticalCenter: parent.verticalCenter

                      Text {
                        id: seqCatText
                        anchors.centerIn: parent
                        text: seqCard.modelData ? (seqCard.modelData.category || "General") : ""
                        color: root.accent
                        font.family: root.fontFamily
                        font.pixelSize: Style.font.caption
                        font.bold: true
                      }
                    }
                  }

                  // Tags
                  Text {
                    visible: seqCard.modelData && Array.isArray(seqCard.modelData.tags) && seqCard.modelData.tags.length > 0
                    text: seqCard.modelData && Array.isArray(seqCard.modelData.tags) ? seqCard.modelData.tags.map(function(t) { return "#" + t }).join(" ") : ""
                    color: root.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                  }

                  // Description
                  Text {
                    visible: seqCard.modelData && !!seqCard.modelData.description
                    text: seqCard.modelData ? (seqCard.modelData.description || "") : ""
                    color: root.dim
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.bodySmall
                    wrapMode: Text.WordWrap
                    width: parent.width
                    maximumLineCount: seqCard.isExpanded ? 100 : 2
                    elide: Text.ElideRight
                  }

                  // Show More / Show Less Toggle
                  Text {
                    text: seqCard.isExpanded ? "▲ Hide commands preview" : "▼ Show commands (" + ((seqCard.modelData && seqCard.modelData.commands) ? seqCard.modelData.commands.split("\n").length : 0) + " steps)"
                    color: root.accent
                    font.family: root.fontFamily
                    font.pixelSize: Style.font.caption
                    font.bold: true

                    MouseArea {
                      anchors.fill: parent
                      cursorShape: Qt.PointingHandCursor
                      onClicked: seqCard.isExpanded = !seqCard.isExpanded
                    }
                  }

                  // Commands Code Preview Box (visible when expanded)
                  BorderSurface {
                    visible: seqCard.isExpanded
                    width: parent.width
                    implicitHeight: cmdPreviewCol.implicitHeight + Style.space(12)
                    color: Qt.rgba(0, 0, 0, 0.35)
                    radius: Style.cornerRadius
                    borderSpec: Border.controlSpec("normal", Qt.darker(root.foreground, 1.8), root.accent)

                    Column {
                      id: cmdPreviewCol
                      anchors.left: parent.left
                      anchors.right: parent.right
                      anchors.top: parent.top
                      anchors.margins: Style.space(6)
                      spacing: Style.space(4)

                      Repeater {
                        model: seqCard.modelData && seqCard.modelData.commands ? seqCard.modelData.commands.split("\n") : []
                        Text {
                          required property string modelData
                          required property int index
                          text: "$ " + (index + 1) + ".  " + modelData
                          color: root.accent
                          font.family: "monospace"
                          font.pixelSize: Style.font.caption
                          wrapMode: Text.WrapAnywhere
                          width: cmdPreviewCol.width
                        }
                      }
                    }
                  }

                  // Actions: Run in Terminal button & Delete button
                  Row {
                    width: parent.width
                    spacing: Style.space(8)

                    Button {
                      text: "▶ Run in Terminal"
                      fontSize: Style.font.bodySmall
                      foreground: root.foreground
                      accent: root.accent
                      selected: true
                      bordered: true
                      width: parent.width - Style.space(40)
                      onClicked: if (seqCard.modelData) root.runSequence(seqCard.modelData.id)
                    }

                    Button {
                      text: "🗑"
                      fontSize: Style.font.bodySmall
                      foreground: bar ? bar.urgent : Color.urgent
                      bordered: true
                      width: Style.space(32)
                      tooltipText: "Delete sequence"
                      onClicked: if (seqCard.modelData) root.deleteSequence(seqCard.modelData.id)
                    }
                  }
                }
              }
            }
          }

          Item { width: 1; height: Style.space(8) }
        }
      }
    }
  }
}
