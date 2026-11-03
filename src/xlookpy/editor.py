"""Python colouring and adjustable type, independent of reduction execution.

Uses Python's tokenizer and Qt's non-destructive display formatting. No code is
evaluated for highlighting. Monokai is a visual inspiration, not a Sublime clone.
"""
import builtins
import io
import keyword
import token
import tokenize
from PySide6 import QtCore, QtGui, QtWidgets


THEMES = {
    "Monokai": {"background": "#272822", "text": "#F8F8F2", "selection": "#49483E",
                "line": "#34352E", "gutter": "#22231E", "muted": "#9E9E92",
                "keyword": "#F92672", "function": "#A6E22E", "builtin": "#66D9EF",
                "string": "#E6DB74", "number": "#AE81FF", "comment": "#A0A095",
                "operator": "#F92672", "parameter": "#FD971F"},
    "Light": {"background": "#FAFAFA", "text": "#263238", "selection": "#CCE3FA",
              "line": "#EDF2F7", "gutter": "#F0F2F4", "muted": "#657680",
              "keyword": "#A31572", "function": "#326B22", "builtin": "#006E8A",
              "string": "#8A5700", "number": "#6F42C1", "comment": "#65745A",
              "operator": "#A31572", "parameter": "#9B4D00"},
}


def python_spans(source):
    """Return (line, start, end, style) spans; tolerate partially typed code."""
    tokens = []
    error = None
    stream = tokenize.generate_tokens(io.StringIO(source).readline)
    try:
        for item in stream:
            tokens.append(item)
    except IndentationError:
        # Incomplete pasted/edited indentation must not remove colouring from
        # the rest of the file. Lex without indentation, then restore columns.
        original = source.split("\n")
        normalized = [line.lstrip(" \t") for line in original]
        offsets = [len(a)-len(b) for a, b in zip(original, normalized)]
        return [(row, a+offsets[row], b+offsets[row], style)
                for row, a, b, style in python_spans("\n".join(normalized))]
    except (tokenize.TokenError, SyntaxError) as exc:
        error = exc
    lines = source.split("\n")
    spans = []
    previous = None
    built_in = set(dir(builtins))
    for i, item in enumerate(tokens):
        kind, value, begin, end, _ = item
        style = None
        if kind == token.COMMENT:
            style = "comment"
        elif kind == token.STRING or token.tok_name.get(kind, "").startswith("FSTRING"):
            style = "string"
        elif kind == token.NUMBER:
            style = "number"
        elif kind == token.NAME:
            if keyword.iskeyword(value):
                style = "keyword"
            elif previous in ("def", "class"):
                style = "function"
            elif value in ("self", "cls"):
                style = "parameter"
            elif value in built_in:
                style = "builtin"
            elif i+1 < len(tokens) and tokens[i+1].string == "(":
                style = "function"
        elif kind == token.OP and value not in ".,()[]{}:":
            style = "operator"
        if style:
            for row in range(begin[0], end[0]+1):
                if not 1 <= row <= len(lines):
                    continue
                a = begin[1] if row == begin[0] else 0
                b = end[1] if row == end[0] else len(lines[row-1])
                spans.append((row-1, a, b, style))
        if kind not in (token.NL, token.NEWLINE, token.INDENT, token.DEDENT, token.COMMENT):
            previous = value
    # The tokenizer reports an unfinished triple-quoted string at its opening.
    if isinstance(error, tokenize.TokenError) and "multi-line string" in str(error.args[0]):
        row, col = error.args[1]
        for r in range(row-1, len(lines)):
            spans.append((r, col if r == row-1 else 0, len(lines[r]), "string"))
    return spans


class PythonHighlighter(QtGui.QSyntaxHighlighter):
    def __init__(self, document, theme="Monokai"):
        super().__init__(document)
        self.spans = {}
        self.source = None
        self.set_theme(theme)

    def set_theme(self, theme):
        self.formats = {}
        for name, color in THEMES[theme].items():
            fmt = QtGui.QTextCharFormat()
            fmt.setForeground(QtGui.QColor(color))
            fmt.setFontWeight(QtGui.QFont.Weight.Normal)
            fmt.setFontItalic(name == "comment")
            fmt.setFontUnderline(False)
            self.formats[name] = fmt
        self.refresh()

    def update_spans(self):
        source = self.document().toPlainText()
        if source != self.source:
            self.source = source
            self.spans = {}
            for row, start, end, style in python_spans(source):
                self.spans.setdefault(row, []).append((start, end, style))

    def refresh(self):
        self.update_spans()
        self.rehighlight()

    def highlightBlock(self, text):
        # Qt invokes this before a deferred whole-document refresh too. Always
        # use CURRENT source offsets; inserting lines must never reuse old rows.
        self.update_spans()
        self.setFormat(0, len(text.encode("utf-16-le"))//2, self.formats["text"])
        for start, end, style in self.spans.get(self.currentBlock().blockNumber(), []):
            a = len(text[:start].encode("utf-16-le"))//2
            b = len(text[:end].encode("utf-16-le"))//2
            self.setFormat(a, b-a, self.formats[style])


class LineNumbers(QtWidgets.QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QtCore.QSize(self.editor.gutter_width(), 0)

    def paintEvent(self, event):
        editor = self.editor
        painter = QtGui.QPainter(self)
        painter.fillRect(event.rect(), QtGui.QColor(THEMES[editor.theme]["gutter"]))
        painter.setFont(editor.font())
        painter.setPen(QtGui.QColor(THEMES[editor.theme]["muted"]))
        block = editor.firstVisibleBlock()
        top = round(editor.blockBoundingGeometry(block).translated(editor.contentOffset()).top())
        while block.isValid() and top <= event.rect().bottom():
            height = round(editor.blockBoundingRect(block).height())
            if block.isVisible() and top+height >= event.rect().top():
                painter.drawText(0, top, self.width()-9, editor.fontMetrics().height(),
                                 QtCore.Qt.AlignmentFlag.AlignRight, str(block.blockNumber()+1))
            top += height
            block = block.next()


class CodeEditor(QtWidgets.QPlainTextEdit):
    sourceChanged = QtCore.Signal()
    fontSizeChanged = QtCore.Signal(int)

    def __init__(self, parent=None, settings=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else QtCore.QSettings("XlookPython", "Editor")
        self._source = ""
        self.theme = str(self.settings.value("theme", "Monokai"))
        if self.theme not in THEMES:
            self.theme = "Monokai"
        self.gutter = LineNumbers(self)
        self.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.SystemFont.FixedFont))
        self.highlighter = PythonHighlighter(self.document(), self.theme)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(0)
        self.timer.timeout.connect(self.highlighter.refresh)
        self.textChanged.connect(self.changed)
        self.blockCountChanged.connect(self.update_gutter)
        self.updateRequest.connect(self.scroll_gutter)
        self.cursorPositionChanged.connect(self.current_line)
        try:
            size = int(self.settings.value("font_size", 14))
        except (ValueError, TypeError):
            size = 14
        self.set_font_size(size)
        self.set_theme(self.theme)
        for label, keys, callback in [
            ("Increase editor font", [QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.ZoomIn), QtGui.QKeySequence("Ctrl+=")], lambda: self.set_font_size(self.font().pointSize()+1)),
            ("Decrease editor font", [QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.ZoomOut)], lambda: self.set_font_size(self.font().pointSize()-1)),
            ("Reset editor font", [QtGui.QKeySequence("Ctrl+0")], lambda: self.set_font_size(14)),
        ]:
            action = QtGui.QAction(label, self)
            action.setShortcuts(keys)
            action.setShortcutContext(QtCore.Qt.ShortcutContext.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.addAction(action)

    def changed(self):
        source = self.toPlainText()
        if source != self._source:
            self._source = source
            self.timer.start()
            self.sourceChanged.emit()

    def refresh_highlighting(self):
        self.timer.stop()
        self.highlighter.refresh()

    def set_font_size(self, points):
        points = max(8, min(32, int(points)))
        font = self.font()
        font.setPointSize(points)
        self.setFont(font)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ")*4)
        self.settings.setValue("font_size", points)
        self.update_gutter()
        self.fontSizeChanged.emit(points)

    def set_theme(self, name):
        if name not in THEMES:
            return
        self.theme = name
        colors = THEMES[name]
        self.setStyleSheet(f"QPlainTextEdit {{ background-color: {colors['background']}; color: {colors['text']}; selection-background-color: {colors['selection']}; border: none; padding: 3px; }}")
        self.settings.setValue("theme", name)
        self.highlighter.set_theme(name)
        self.gutter.update()
        self.current_line()

    def current_line(self):
        selection = QtWidgets.QTextEdit.ExtraSelection()
        selection.format.setBackground(QtGui.QColor(THEMES[self.theme]["line"]))
        selection.format.setProperty(QtGui.QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])

    def gutter_width(self):
        return 16 + self.fontMetrics().horizontalAdvance("9")*len(str(max(1, self.blockCount())))

    def update_gutter(self, *args):
        self.setViewportMargins(self.gutter_width(), 0, 0, 0)
        rect = self.contentsRect()
        self.gutter.setGeometry(rect.left(), rect.top(), self.gutter_width(), rect.height())
        self.gutter.update()

    def scroll_gutter(self, rect, dy):
        if dy:
            self.gutter.scroll(0, dy)
        else:
            self.gutter.update(0, rect.y(), self.gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self.update_gutter()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.gutter.setGeometry(rect.left(), rect.top(), self.gutter_width(), rect.height())


def editor_panel(editor):
    """Visible font and theme controls above the editable source."""
    panel = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    controls = QtWidgets.QHBoxLayout()
    controls.addWidget(QtWidgets.QLabel("Font"))
    size = QtWidgets.QSpinBox()
    size.setObjectName("editorFontSize")
    size.setRange(8, 32)
    size.setSuffix(" pt")
    size.setValue(editor.font().pointSize())
    size.valueChanged.connect(editor.set_font_size)
    editor.fontSizeChanged.connect(size.setValue)
    controls.addWidget(size)
    controls.addWidget(QtWidgets.QLabel("Theme"))
    theme = QtWidgets.QComboBox()
    theme.setObjectName("editorTheme")
    theme.addItems(THEMES)
    theme.setCurrentText(editor.theme)
    theme.currentTextChanged.connect(editor.set_theme)
    controls.addWidget(theme)
    controls.addStretch()
    layout.addLayout(controls)
    layout.addWidget(editor)
    return panel
