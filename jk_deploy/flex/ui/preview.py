"""Display-only selection shared with the GPU renderer through an atomic tmpfs file."""
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot


class Preview(QObject):
    changed = Signal()

    def __init__(self, path=Path('/run/jk-srv-preview.state')):
        super().__init__()
        self.path = path
        self.selection = -1
        self.message = ''
        self.set_selection(-1)

    @Property(int, notify=changed)
    def selected(self):
        return self.selection

    @Property(str, notify=changed)
    def error(self):
        return self.message

    def set_selection(self, selected):
        try:
            temporary = self.path.with_suffix('.tmp')
            temporary.write_text(f'{selected}\n')
            temporary.replace(self.path)
        except OSError as error:
            self.message = f'Preview selection failed: {error}'
        else:
            self.selection = selected
            self.message = ''
        self.changed.emit()

    @Slot(int)
    def toggle(self, camera):
        if 0 <= camera < 4:
            self.set_selection(camera if self.selection < 0 else -1)
