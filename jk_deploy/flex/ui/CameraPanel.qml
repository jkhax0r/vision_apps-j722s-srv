import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Popup {
    id: panel
    objectName: "cameraPanel"
    width: 840
    height: 650
    x: parent.width - width - 24
    y: (parent.height - height) / 2
    padding: 24
    focus: true
    closePolicy: Popup.CloseOnEscape
    onOpened: { allCameras.checked = false; cameraSettings.refresh() }
    background: Rectangle { color: "#fa191d1c"; border.color: "#6a7771"; radius: 8 }

    property var controls: cameraSettings.controls
    property bool ready: !cameraSettings.busy && !calibration.busy && cameraSettings.cameras.length > 0
    property int exposureMode: controls.exposure_mode ? controls.exposure_mode.value : 1
    function value(name, fallback) { return controls[name] ? controls[name].value : fallback }
    function change(name, value) { cameraSettings.setControl(name, value, allCameras.checked) }

    component FieldLabel: Label {
        color: "#f7faf9"
        font.pixelSize: 19
        Layout.preferredWidth: 190
        wrapMode: Text.WordWrap
    }
    component IconButton: Button {
        implicitWidth: 44
        implicitHeight: 40
        icon.width: 26
        icon.height: 26
        icon.color: "#f7faf9"
        display: AbstractButton.IconOnly
        background: Rectangle { color: parent.down ? "#40534b" : "#29352f"; radius: 5 }
    }
    component ControlSlider: RowLayout {
        id: setting
        required property string controlName
        required property string title
        property real divisor: 1
        property string suffix: ""
        property bool logarithmic: false
        property var info: panel.controls[controlName] || ({min: 0, max: 1, value: 0})
        property real lower: controlName === "ae_exposure_max" ? Math.max(info.min, panel.value("ae_exposure_upper", 1)) : info.min
        property real frameLimit: Math.floor(1000000 / Math.max(1, panel.value("max_fps", 30)))
        property real upper: controlName === "exposure" ? Math.min(info.max, frameLimit)
                            : (controlName === "ae_exposure_max" ? Math.min(info.max, Math.max(frameLimit, info.default)) : info.max)
        property real current: slider.pressed ? rawValue(slider.value) : info.value
        function rawValue(position) { return Math.round(logarithmic ? Math.pow(10, position) : position) }
        spacing: 16
        Layout.fillWidth: true
        Layout.preferredHeight: 44
        opacity: enabled ? 1 : 0.45
        FieldLabel { text: setting.title }
        Slider {
            id: slider
            objectName: setting.controlName + "Slider"
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            from: setting.logarithmic ? Math.log10(Math.max(1, setting.lower)) : setting.lower
            to: setting.logarithmic ? Math.log10(Math.max(1, setting.upper)) : setting.upper
            value: setting.logarithmic ? Math.log10(Math.max(1, setting.info.value)) : setting.info.value
            stepSize: setting.logarithmic ? 0 : 1
            onPressedChanged: if (!pressed && panel.ready) panel.change(setting.controlName, setting.rawValue(value))
            onMoved: if (!pressed && panel.ready) panel.change(setting.controlName, setting.rawValue(value))
        }
        Label {
            Layout.preferredWidth: 110
            horizontalAlignment: Text.AlignRight
            color: "#c9e6d9"
            font.pixelSize: 20
            text: (setting.current / setting.divisor).toFixed(setting.divisor === 1 ? 0 : 1) + setting.suffix
        }
    }

    contentItem: ColumnLayout {
        spacing: 6
        RowLayout {
            Layout.fillWidth: true
            Label { text: "Camera settings"; color: "#f7faf9"; font.pixelSize: 26; font.bold: true; Layout.fillWidth: true }
            IconButton { objectName: "closeCameraPanel"; icon.source: "x.svg"; onClicked: panel.close(); ToolTip.visible: hovered; ToolTip.text: "Close" }
        }
        RowLayout {
            Layout.fillWidth: true
            ComboBox {
                objectName: "cameraSelector"
                Layout.fillWidth: true
                implicitHeight: 44
                font.pixelSize: 20
                model: cameraSettings.cameras
                textRole: "label"
                currentIndex: cameraSettings.selected
                enabled: panel.ready
                onActivated: cameraSettings.select(currentIndex)
            }
            CheckBox {
                id: allCameras
                objectName: "allCameras"
                text: "Apply to all"
                font.pixelSize: 19
                palette.windowText: "#f7faf9"
                enabled: panel.ready
                ToolTip.visible: hovered
                ToolTip.text: "Apply subsequent changes to all four cameras"
            }
        }
        Label { text: cameraSettings.identity; font.pixelSize: 16; color: "#adbcb4" }
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            FieldLabel { text: "Exposure mode" }
            ComboBox {
                objectName: "exposureMode"
                Layout.fillWidth: true
                implicitHeight: 44
                font.pixelSize: 20
                model: [{text: "Auto", value: 1}, {text: "Auto gain", value: 2}, {text: "Manual", value: 0}]
                textRole: "text"
                currentIndex: panel.exposureMode === 1 ? 0 : (panel.exposureMode === 2 ? 1 : 2)
                enabled: panel.ready
                onActivated: panel.change("exposure_mode", model[currentIndex].value)
            }
        }
        ControlSlider { controlName: "brightness"; title: "Brightness"; divisor: 40.96; suffix: "%"; enabled: panel.ready }
        ControlSlider { controlName: "exposure"; title: "Shutter setpoint"; divisor: 1000; suffix: " ms"; logarithmic: true; enabled: panel.ready && panel.exposureMode !== 1 }
        ControlSlider { controlName: "gain"; title: "Gain setpoint"; enabled: panel.ready && panel.exposureMode === 0 }
        ControlSlider { controlName: "ae_exposure_max"; title: "Auto shutter limit"; divisor: 1000; suffix: " ms"; logarithmic: true; enabled: panel.ready && panel.exposureMode === 1 }
        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 44
            FieldLabel { text: "Anti-flicker" }
            ComboBox {
                objectName: "antiFlicker"
                Layout.fillWidth: true
                implicitHeight: 44
                font.pixelSize: 20
                model: ["Off", "50 Hz", "60 Hz", "Auto"]
                currentIndex: panel.value("power_line_frequency", 0)
                enabled: panel.ready
                onActivated: panel.change("power_line_frequency", currentIndex)
            }
        }
        Label {
            Layout.fillWidth: true
            font.pixelSize: 16
            color: "#efbe80"
            text: (panel.exposureMode === 1 ? panel.value("ae_exposure_max", 0) : panel.value("exposure", 0)) > 1000000 / panel.value("max_fps", 30)
                  ? "Long shutter times can reduce frame rate." : ""
        }
        RowLayout {
            Layout.fillWidth: true
            Label {
                Layout.fillWidth: true
                font.pixelSize: 16
                color: cameraSettings.hasError ? "#ffad91" : "#b8e4d1"
                text: cameraSettings.status
                wrapMode: Text.WordWrap
                maximumLineCount: 2
                elide: Text.ElideRight
            }
            Button {
                objectName: "cameraDefaults"
                text: "Reset defaults"
                icon.source: "rotate-ccw.svg"
                font.pixelSize: 18
                implicitHeight: 42
                enabled: panel.ready
                onClicked: cameraSettings.defaults(allCameras.checked)
            }
        }
    }
}
