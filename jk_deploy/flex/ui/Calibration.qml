import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 1920
    height: 720
    visible: true
    color: "transparent"
    flags: Qt.FramelessWindowHint
    property bool confirmationVisible: confirm.opened
    property bool toolsVisible: tools.opened
    property bool settingsVisible: settings.opened
    property bool removalVisible: removal.opened
    property bool retryVisible: retryConfirm.opened

    Connections {
        target: calibration
        function onChanged() {
            if (calibration.waitingForRemoval) removal.open()
            else removal.close()
        }
    }

    MouseArea {
        objectName: "previewTouch"
        width: root.width / 2
        height: root.height
        enabled: !calibration.busy && !root.toolsVisible && !root.confirmationVisible
        onClicked: function(mouse) {
            preview.toggle((mouse.y >= height / 2 ? 2 : 0) + (mouse.x >= width / 2 ? 1 : 0))
        }
    }

    Rectangle {
        objectName: "previewBorder"
        visible: preview.selected >= 0
        width: root.width / 2
        height: root.height
        color: "transparent"
        border.color: "#7adab3"
        border.width: 4
    }

    Label {
        visible: preview.error.length > 0
        x: 20
        y: 20
        width: root.width / 2 - 40
        padding: 12
        text: preview.error
        wrapMode: Text.WordWrap
        color: "#ffffff"
        background: Rectangle { color: "#962e2e" }
    }

    // Screen-space badge over the center of the right-hand stitched viewport.
    Image {
        objectName: "heliosBadge"
        width: 198
        height: width * 255 / 247
        x: root.width * 0.75 - width / 2
        y: root.height / 2 - height / 2
        source: "helios-h.svg"
        opacity: 0.85
        sourceSize.width: width * 2
        sourceSize.height: height * 2
        fillMode: Image.PreserveAspectFit
        smooth: true
        Accessible.name: "Helios Technologies"
        Accessible.role: Accessible.Graphic
    }

    component ActionButton: Button {
        implicitHeight: 58
        implicitWidth: 170
        font.pixelSize: 21
        font.bold: true
        palette.buttonText: "#f7faf9"
        background: Rectangle {
            radius: 6
            color: parent.down ? "#236553" : "#193d33"
            border.color: parent.enabled ? "#7adab3" : "#707873"
            border.width: 1
            opacity: parent.enabled ? 1 : 0.65
        }
    }

    ActionButton {
        id: calButton
        objectName: "calButton"
        x: 20
        y: root.height - height - 18
        text: "CAL"
        icon.source: "scan-line.svg"
        icon.color: "#f7faf9"
        icon.width: 28
        icon.height: 28
        enabled: !calibration.busy && !cameraSettings.busy
        onClicked: { settings.close(); tools.open() }
        ToolTip.visible: hovered
        ToolTip.text: "Calibration and camera settings"
    }

    Popup {
        id: tools
        objectName: "cameraTools"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 440
        height: 286
        padding: 24
        modal: true
        focus: true
        background: Rectangle { color: "#191d1c"; border.color: "#6a7771"; radius: 8 }
        Overlay.modal: Rectangle { color: "#55000000" }
        contentItem: ColumnLayout {
            spacing: 16
            Label { text: "Camera tools"; color: "#f7faf9"; font.pixelSize: 26; font.bold: true }
            ActionButton {
                objectName: "recalibrateMenu"
                Layout.fillWidth: true
                text: "Recalibrate"
                icon.source: "scan-line.svg"
                icon.color: "#f7faf9"
                onClicked: { tools.close(); confirm.open() }
            }
            ActionButton {
                objectName: "settingsMenu"
                Layout.fillWidth: true
                text: "Camera settings"
                icon.source: "sliders-horizontal.svg"
                icon.color: "#f7faf9"
                onClicked: { tools.close(); settings.open() }
            }
        }
    }

    CameraPanel { id: settings; parent: Overlay.overlay }

    Popup {
        id: confirm
        objectName: "confirmation"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 600
        height: 290
        padding: 28
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        background: Rectangle { color: "#191d1c"; border.color: "#6a7771"; radius: 8 }
        Overlay.modal: Rectangle { color: "#77000000" }
        contentItem: ColumnLayout {
            spacing: 20
            Label { text: "Calibrate four cameras?"; font.pixelSize: 27; font.bold: true; color: "#f7faf9" }
            Label {
                Layout.fillWidth: true
                text: "Start with all four green corner markers installed. After capture, you will be asked to remove them for a second capture. Keep the cameras, table and cloth in place."
                font.pixelSize: 19
                color: "#d1d9d5"
                wrapMode: Text.WordWrap
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 16
                ActionButton { text: "Cancel"; onClicked: confirm.close() }
                ActionButton {
                    text: "Start CAL"
                    objectName: "startCalButton"
                    onClicked: { confirm.close(); calibration.start() }
                }
            }
        }
    }

    Popup {
        id: retryConfirm
        objectName: "retryConfirmation"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 660
        height: 300
        padding: 28
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape
        background: Rectangle { color: "#191d1c"; border.color: "#6a7771"; radius: 8 }
        Overlay.modal: Rectangle { color: "#77000000" }
        contentItem: ColumnLayout {
            spacing: 20
            Label { text: "Retry saved calibration?"; font.pixelSize: 27; font.bold: true; color: "#f7faf9" }
            Label {
                Layout.fillWidth: true
                text: "Only retry if the cameras, table and cloth have not moved since capture. No new images will be taken. Otherwise, cancel and start a new CAL."
                font.pixelSize: 21
                color: "#d1d9d5"
                wrapMode: Text.WordWrap
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 16
                ActionButton { objectName: "cancelRetry"; text: "Cancel"; onClicked: retryConfirm.close() }
                ActionButton {
                    objectName: "confirmRetry"
                    text: "Retry"
                    enabled: calibration.canRetry && !cameraSettings.busy
                    onClicked: { retryConfirm.close(); calibration.retry() }
                }
            }
        }
    }

    Popup {
        id: removal
        objectName: "cornerRemovalPrompt"
        parent: Overlay.overlay
        anchors.centerIn: parent
        width: 800
        height: calibration.detail.length > 0 ? 430 : 350
        padding: 30
        modal: true
        focus: true
        closePolicy: Popup.NoAutoClose
        background: Rectangle { color: "#191d1c"; border.color: "#7adab3"; border.width: 3; radius: 8 }
        Overlay.modal: Rectangle { color: "#99000000" }
        contentItem: ColumnLayout {
            spacing: 18
            Label {
                text: "Remove all four green corners"
                color: "#f7faf9"
                font.pixelSize: 30
                font.bold: true
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            Label {
                text: "The marked capture is saved. Remove the four green corner holders to uncover the checkerboard.\n\nDo not move the cameras, table or cloth. Step away, then tap Continue."
                color: "#d8e5dd"
                font.pixelSize: 22
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            Label {
                visible: calibration.detail.length > 0
                text: calibration.detail
                color: "#f3b597"
                font.pixelSize: 18
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
            }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 20
                ActionButton {
                    objectName: "cancelCornerRemoval"
                    text: "Cancel CAL"
                    onClicked: calibration.cancel()
                }
                ActionButton {
                    objectName: "continueCornerRemoval"
                    text: "Continue"
                    onClicked: calibration.continueCapture()
                }
            }
        }
    }

    Rectangle {
        id: statusPanel
        visible: calibration.state !== "idle"
        x: 208
        y: root.height - height - 18
        width: 730
        height: calibration.busy ? 112 : 170
        radius: 6
        color: "#ef181c1b"
        border.color: calibration.state === "failed" || calibration.hasWarning ? "#e99b76" : "#718d80"
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 8
            RowLayout {
                Layout.fillWidth: true
                Label {
                    Layout.fillWidth: true
                    text: calibration.phase
                    font.pixelSize: 20
                    font.bold: true
                    color: "#f7faf9"
                    elide: Text.ElideRight
                }
                Label { text: calibration.elapsed; font.pixelSize: 21; color: "#b8e4d1" }
            }
            Label {
                visible: !calibration.busy
                Layout.fillWidth: true
                Layout.fillHeight: true
                text: calibration.detail || (calibration.state === "complete" ? "New calibration is live." : "Previous calibration retained.")
                wrapMode: Text.WordWrap
                maximumLineCount: 3
                elide: Text.ElideRight
                font.pixelSize: 17
                color: "#d8dfdb"
            }
            RowLayout {
                Layout.alignment: Qt.AlignRight
                spacing: 12
                Button {
                    objectName: "retrySavedButton"
                    visible: calibration.canRetry
                    enabled: !cameraSettings.busy
                    implicitHeight: 40
                    implicitWidth: 220
                    font.pixelSize: 18
                    text: "Retry saved captures"
                    onClicked: retryConfirm.open()
                }
                Button {
                    implicitHeight: 40
                    implicitWidth: 132
                    font.pixelSize: 18
                    text: calibration.busy ? "Cancel CAL" : "Dismiss"
                    onClicked: calibration.busy ? calibration.cancel() : calibration.dismiss()
                }
            }
        }
    }
}
