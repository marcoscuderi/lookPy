import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import pytest
pytest.importorskip("PySide6")
from PySide6 import QtCore, QtGui, QtWidgets
from xlookpy.editor import CodeEditor, python_spans, editor_panel


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def test_python_token_colours_respect_strings_comments_and_functions():
    code = 'def reduce(session):\n    # if 123 "string"\n    x = "if 123 # not a comment"\n    return len([42])\n'
    spans = python_spans(code)
    assert (0, 0, 3, "keyword") in spans
    assert (0, 4, 10, "function") in spans
    assert (1, 4, 21, "comment") in spans
    assert not any(style == "number" and row in (1, 2) for row, a, b, style in spans)
    assert any(row == 3 and style == "builtin" for row, a, b, style in spans)
    assert any(row == 3 and style == "number" for row, a, b, style in spans)


def test_multiline_and_incomplete_python():
    code = '"""doc\nif 123\nend"""\nx = 12\n'
    spans = python_spans(code)
    assert (1, 0, 6, "string") in spans
    assert not any(row == 1 and style == "keyword" for row, a, b, style in spans)
    assert (3, 4, 6, "number") in spans
    assert (1, 0, 6, "string") in python_spans('"""doc\nif 123')
    assert python_spans('def reduce(\n')  # Incomplete expression must not crash.


def test_highlighting_is_visual_only_and_handles_non_bmp_characters(app, tmp_path):
    editor = CodeEditor(settings=QtCore.QSettings(str(tmp_path/"editor.ini"), QtCore.QSettings.Format.IniFormat))
    code = 'x = "🌍"; y = 42 # comment\n'
    editor.setPlainText(code)
    editor.document().setModified(False)
    editor.highlighter.refresh()
    app.processEvents()
    assert editor.toPlainText() == code
    assert not editor.document().isModified()
    formats = editor.document().firstBlock().layout().formats()
    start = len(code[:code.index("42")].encode("utf-16-le"))//2
    assert any(f.start == start and f.length == 2 and f.format.foreground().color().name() == "#ae81ff" for f in formats)
    editor.close()


def test_editor_controls_persist_and_do_not_edit_source(app, tmp_path):
    settings = QtCore.QSettings(str(tmp_path/"editor.ini"), QtCore.QSettings.Format.IniFormat)
    editor = CodeEditor(settings=settings)
    panel = editor_panel(editor)
    editor.setPlainText("x = 10\n")
    changes = []
    editor.sourceChanged.connect(lambda: changes.append(True))
    size = panel.findChild(QtWidgets.QSpinBox, "editorFontSize")
    theme = panel.findChild(QtWidgets.QComboBox, "editorTheme")
    size.setValue(18)
    theme.setCurrentText("Light")
    editor.highlighter.refresh()
    app.processEvents()
    assert editor.font().pointSize() == 18
    assert editor.theme == "Light"
    assert editor.toPlainText() == "x = 10\n"
    assert changes == []
    second = CodeEditor(settings=settings)
    assert second.font().pointSize() == 18 and second.theme == "Light"
    action = next(a for a in editor.actions() if a.text() == "Increase editor font")
    action.trigger()
    assert size.value() == 19
    assert editor.toPlainText() == "x = 10\n"
    panel.close()
    second.close()


def test_highlighting_follows_current_rows_before_and_after_deferred_refresh(app, tmp_path):
    editor=CodeEditor(settings=QtCore.QSettings(str(tmp_path/"colors.ini"), QtCore.QSettings.Format.IniFormat))
    def colour(row, column):
        block=editor.document().findBlockByNumber(row)
        ranges=block.layout().formats()
        matching=[r for r in ranges if r.start <= column < r.start+r.length]
        return QtGui.QTextCharFormat(matching[-1].format) if matching else QtGui.QTextCharFormat()
    code='# a comment\nvalue = 42\nif value:\n    print(value)\n'
    for _ in range(10):
        editor.setPlainText(code)
        editor.refresh_highlighting()
        cursor=editor.textCursor()
        cursor.setPosition(0)
        cursor.insertText('# another comment\n')
        editor.highlighter.rehighlight()  # Before the timer: no stale row spans.
        assert colour(2,8).foreground().color().name() == '#ae81ff'
        assert not colour(2,0).fontItalic()
        app.processEvents()
        assert colour(3,0).foreground().color().name() == '#f92672'
        editor.undo()
        app.processEvents()
        editor.refresh_highlighting()
        assert editor.toPlainText() == code
        assert colour(1,8).foreground().color().name() == '#ae81ff'
        assert not colour(1,0).fontItalic()
    editor.close()


def test_recovery_from_bad_indentation_and_triple_quote_edits(app, tmp_path):
    editor=CodeEditor(settings=QtCore.QSettings(str(tmp_path/"recover.ini"), QtCore.QSettings.Format.IniFormat))
    bad='if True:\n    x = 1\n  y = 2\nanswer = 42\n'
    assert (3,9,11,'number') in python_spans(bad)
    editor.setPlainText('"""unfinished\nanswer = 42\n')
    editor.refresh_highlighting()
    cursor=editor.textCursor();cursor.setPosition(0);cursor.deleteChar();cursor.deleteChar();cursor.deleteChar()
    app.processEvents();editor.refresh_highlighting()
    block=editor.document().findBlockByNumber(1)
    formats=block.layout().formats()
    assert any(r.start == 9 and r.format.foreground().color().name() == '#ae81ff' for r in formats)
    assert not editor.document().findBlockByNumber(1).layout().formats()[0].format.fontItalic()
    editor.close()
