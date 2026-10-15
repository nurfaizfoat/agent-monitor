import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "nurfaizfoat.agent-monitor"
  ipcTarget: moduleName
  manageIpc: false

  readonly property color foreground: bar ? bar.foreground : Color.foreground
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property color blue: "#5786FE"
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  property var balances: []
  property bool available: false
  property bool loading: false
  property string errorText: ""
  property double lastUpdated: 0
  property var openaiLimits: []
  property string openaiPlan: "Subscription"
  property bool openaiLoading: false
  property string openaiError: ""
  property double openaiUpdated: 0
  property double nowMs: Date.now()
  property bool deepseekNeedsSetup: false
  property bool openaiNeedsSetup: false
  property bool setupPromptShown: false
  property string setupError: ""
  readonly property bool alarming: openaiLimits.some(function(w) { return w.used >= 90 })

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function money(value, currency) {
    var prefix = currency === "USD" ? "$" : currency === "CNY" ? "¥" : currency + " "
    var amount = Number(value)
    return prefix + (isFinite(amount) ? amount.toFixed(2) : String(value))
  }

  function refresh() {
    refreshOpenAI()
    if (loading) return
    loading = true
    errorText = ""
    balanceProcess.command = ["python3", Qt.resolvedUrl("balance.py").toString().replace(/^file:\/\//, "")]
    balanceProcess.running = true
  }

  function receive(text) {
    loading = false
    try {
      var data = JSON.parse(text)
      deepseekNeedsSetup = data.needs_setup === true
      maybePromptSetup()
      if (data.error) {
        errorText = String(data.error)
      } else if (data.balances instanceof Array) {
        balances = data.balances
        available = data.available === true
        lastUpdated = Date.now()
      } else {
        errorText = "Unexpected response from DeepSeek."
      }
    } catch (e) {
      errorText = "Could not read DeepSeek balance."
    }
  }

  function refreshOpenAI() {
    if (openaiLoading) return
    openaiLoading = true
    openaiError = ""
    openaiProcess.command = ["python3", Qt.resolvedUrl("openai.py").toString().replace(/^file:\/\//, "")]
    openaiProcess.running = true
  }

  function receiveOpenAI(text) {
    openaiLoading = false
    try {
      var data = JSON.parse(text)
      openaiNeedsSetup = data.needs_setup === true
      maybePromptSetup()
      if (data.error) openaiError = String(data.error)
      else if (data.limits instanceof Array) {
        openaiLimits = data.limits
        openaiPlan = String(data.plan)
        openaiUpdated = Date.now()
      } else openaiError = "Unexpected response from OpenAI."
    } catch (e) { openaiError = "Could not read OpenAI limits." }
  }

  function resetText(epoch) {
    if (!epoch) return "Reset time unavailable"
    var minutes = Math.ceil((epoch * 1000 - nowMs) / 60000)
    if (minutes <= 0) return "Reset due · refresh to update"
    var hours = Math.floor(minutes / 60)
    var days = Math.floor(hours / 24)
    var duration = days > 0 ? days + "d " + (hours % 24) + "h" : hours > 0 ? hours + "h " + (minutes % 60) + "m" : minutes + "m"
    return "Resets in " + duration + " · " + Qt.formatDateTime(new Date(epoch * 1000), "ddd h:mm AP")
  }

  function maybePromptSetup() {
    if (!setupPromptShown && button.tooltipHovered && (deepseekNeedsSetup || openaiNeedsSetup)) {
      setupPromptShown = true
      root.open()
    }
  }

  function saveDeepSeekKey() {
    if (saveProcess.running || apiKey.text.trim() === "") return
    setupError = ""
    saveProcess.command = ["python3", Qt.resolvedUrl("setup.py").toString().replace(/^file:\/\//, "")]
    saveProcess.running = true
  }

  Component.onCompleted: refresh()
  onOpenedChanged: if (opened) {
    nowMs = Date.now()
    if (Date.now() - Math.min(lastUpdated, openaiUpdated) > 60000) refresh()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  } else {
    apiKey.clear()
  }

  Timer {
    interval: 300000
    running: true
    repeat: true
    onTriggered: root.refresh()
  }

  Process {
    id: saveProcess
    stdinEnabled: true
    onStarted: {
      write(apiKey.text + "\n")
      apiKey.clear()
    }
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var result = JSON.parse(text)
          if (result.saved) root.refresh()
          else root.setupError = result.error || "Could not save API key."
        } catch (e) { root.setupError = "Could not save API key." }
      }
    }
    onExited: function(code) {
      if (code !== 0) root.setupError = "Could not start credential setup."
    }
  }

  Process {
    id: balanceProcess
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.receive(String(text || ""))
    }
    onExited: function(code) {
      if (code !== 0) {
        root.loading = false
        root.errorText = "Could not start the DeepSeek balance check."
      }
    }
  }

  Timer {
    interval: 30000
    running: root.opened
    repeat: true
    onTriggered: root.nowMs = Date.now()
  }

  Process {
    id: openaiProcess
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.receiveOpenAI(String(text || ""))
    }
    onExited: function(code) {
      if (code !== 0) {
        root.openaiLoading = false
        root.openaiError = "Could not start the OpenAI limits check."
      }
    }
  }

  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.toggle() }
    function refresh(): string { root.refresh(); return "ok" }
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    tooltipText: "Agent Monitor"
    text: "󰓅"
    active: root.alarming
    onTooltipHoveredChanged: root.maybePromptSetup()
    onPressed: function(code) {
      if (code === Qt.MiddleButton) root.refresh()
      else root.toggle()
    }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(380))
    contentHeight: panel.fittedContentHeight(content.implicitHeight, Style.space(650))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: apiKey.activeFocus
      onActivateRequested: root.refresh()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) { if (t === "r" || t === "R") root.refresh() }

      Flickable {
        anchors.fill: parent
        contentWidth: width
        contentHeight: content.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

      Column {
        id: content
        width: parent.width
        spacing: Style.space(14)

        Column {
          visible: root.deepseekNeedsSetup
          width: parent.width
          spacing: Style.space(8)
          Text {
            width: parent.width
            text: "Welcome to Agent Monitor. Add your DeepSeek API key. It stays on this computer and is never included in the plugin. OpenAI connects separately using your ChatGPT login."
            textFormat: Text.PlainText
            color: root.foreground
            font.family: root.fontFamily
            font.pixelSize: Style.font.caption
            wrapMode: Text.WordWrap
          }
          TextField {
            id: apiKey
            width: parent.width
            placeholderText: "DeepSeek API key"
            echoMode: TextInput.Password
            selectByMouse: true
            onAccepted: root.saveDeepSeekKey()
            Keys.onEscapePressed: root.close()
          }
          Button {
            text: saveProcess.running ? "Saving…" : "Save DeepSeek key"
            enabled: !saveProcess.running && apiKey.text.trim() !== ""
            onClicked: root.saveDeepSeekKey()
          }
          Text {
            visible: root.setupError !== ""
            width: parent.width
            text: root.setupError
            textFormat: Text.PlainText
            color: Color.urgent
            wrapMode: Text.WordWrap
          }
        }

        PanelHero {
          width: parent.width
          title: "OpenAI"
          meta: "ChatGPT " + root.openaiPlan + " · Codex limits"
          foreground: root.foreground
          fontFamily: root.fontFamily
          iconComponent: Component {
            OpenAIIcon {
              width: Style.font.display
              height: Style.font.display
              color: root.foreground
            }
          }
        }

        Text {
          visible: root.openaiError !== "" || root.openaiLimits.length === 0
          width: parent.width
          text: root.openaiError !== "" ? root.openaiError + (root.openaiLimits.length ? " Showing last known limits." : "") : root.openaiLoading ? "Checking plan limits…" : "No plan limits reported."
          textFormat: Text.PlainText
          color: root.openaiError !== "" ? Color.urgent : root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Repeater {
          model: root.openaiLimits
          Column {
            required property var modelData
            width: content.width
            spacing: Style.space(6)

            Item {
              width: parent.width
              implicitHeight: limitTitle.implicitHeight
              Text {
                id: limitTitle
                anchors.left: parent.left
                text: modelData.label
                color: root.foreground
                font.family: root.fontFamily
                font.pixelSize: Style.font.body
              }
              Text {
                anchors.right: parent.right
                text: Math.round(modelData.used) + "% used · " + Math.round(100 - modelData.used) + "% left"
                color: modelData.used >= 90 ? Color.urgent : root.dim
                font.family: root.fontFamily
                font.pixelSize: Style.font.caption
              }
            }

            Rectangle {
              width: parent.width
              height: Style.space(5)
              radius: height / 2
              color: Style.selectedFillFor(root.foreground, Color.accent)
              Rectangle {
                // The meter represents allowance LEFT, so a fresh window is full.
                width: parent.width * Math.max(0, Math.min(100, 100 - modelData.used)) / 100
                height: parent.height
                radius: parent.radius
                color: modelData.used >= 90 ? Color.urgent : root.foreground
                Behavior on width { NumberAnimation { duration: 160 } }
              }
            }

            Text {
              width: parent.width
              text: root.resetText(modelData.resetAt)
              color: root.dim
              font.family: root.fontFamily
              font.pixelSize: Style.font.caption
              wrapMode: Text.WordWrap
            }
          }
        }

        Text {
          visible: root.openaiUpdated > 0
          text: "Updated " + Qt.formatTime(new Date(root.openaiUpdated), "h:mm AP")
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }

        PanelSeparator { foreground: root.foreground }

        PanelHero {
          width: parent.width
          title: "DeepSeek"
          meta: "API · prepaid credits"
          foreground: root.foreground
          fontFamily: root.fontFamily
          iconComponent: Component {
            WhaleIcon {
              width: Style.font.display
              height: Style.font.display
              color: root.foreground
            }
          }
        }

        PanelSeparator {
          foreground: root.foreground
        }

        PanelSectionHeader {
          text: "BALANCE LEFT"
          foreground: root.foreground
          fontFamily: root.fontFamily
        }

        Text {
          visible: root.balances.length === 0
          width: parent.width
          text: root.loading ? "Checking balance…" : root.errorText !== "" ? root.errorText : "No balance reported for this API account."
          textFormat: Text.PlainText
          color: root.errorText !== "" ? (root.bar ? root.bar.urgent : Color.urgent) : root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          wrapMode: Text.WordWrap
        }

        Row {
          id: balanceRow
          visible: root.balances.length > 0
          width: parent.width
          height: implicitHeight

          Repeater {
            model: root.balances
            Item {
              required property var modelData
              required property int index
              width: balanceRow.width / root.balances.length
              implicitHeight: metrics.implicitHeight

              Rectangle {
                visible: index > 0
                anchors.left: parent.left
                anchors.top: parent.top
                width: 1
                height: parent.height
                gradient: Gradient {
                  GradientStop { position: 0; color: "transparent" }
                  GradientStop { position: 0.5; color: Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.5) }
                  GradientStop { position: 1; color: "transparent" }
                }
              }

              Column {
                id: metrics
                anchors.left: parent.left
                anchors.leftMargin: index > 0 ? Style.space(12) : 0
                anchors.right: parent.right
                anchors.rightMargin: index < root.balances.length - 1 ? Style.space(12) : 0
                spacing: Style.space(5)

                Text {
                  text: modelData.currency === "CNY" ? "RMB" : modelData.currency
                  textFormat: Text.PlainText
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  font.bold: true
                }

                Text {
                  width: parent.width
                  text: root.money(modelData.total, modelData.currency)
                  textFormat: Text.PlainText
                  color: root.available ? root.foreground : (root.bar ? root.bar.urgent : Color.urgent)
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.display
                  fontSizeMode: Text.HorizontalFit
                  minimumPixelSize: Style.font.body
                  font.bold: true
                }

                Text {
                  width: parent.width
                  text: "Topped up " + root.money(modelData.topped_up, modelData.currency)
                  textFormat: Text.PlainText
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }

                Text {
                  width: parent.width
                  text: "Granted " + root.money(modelData.granted, modelData.currency)
                  textFormat: Text.PlainText
                  color: root.dim
                  font.family: root.fontFamily
                  font.pixelSize: Style.font.caption
                  wrapMode: Text.WordWrap
                }
              }
            }
          }
        }

        Text {
          visible: root.balances.length > 0 && (!root.available || root.errorText !== "")
          text: root.errorText !== "" ? root.errorText + " Showing last known balance." : "Balance unavailable for API calls."
          textFormat: Text.PlainText
          width: parent.width
          color: root.bar ? root.bar.urgent : Color.urgent
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          wrapMode: Text.WordWrap
        }

        Text {
          text: root.lastUpdated ? "Updated " + Qt.formatTime(new Date(root.lastUpdated), "h:mm AP") + "  ·  R to refresh" : "R to refresh"
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
        }
      }
      }
    }
  }
}
