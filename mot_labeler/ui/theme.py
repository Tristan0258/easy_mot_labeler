from PySide6.QtGui import QPalette, QColor


def apply_dark_theme(app) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(31, 34, 40))
    palette.setColor(QPalette.WindowText, QColor(230, 233, 239))
    palette.setColor(QPalette.Base, QColor(24, 26, 31))
    palette.setColor(QPalette.AlternateBase, QColor(37, 41, 48))
    palette.setColor(QPalette.ToolTipBase, QColor(230, 233, 239))
    palette.setColor(QPalette.ToolTipText, QColor(20, 22, 26))
    palette.setColor(QPalette.Text, QColor(230, 233, 239))
    palette.setColor(QPalette.Button, QColor(43, 48, 57))
    palette.setColor(QPalette.ButtonText, QColor(230, 233, 239))
    palette.setColor(QPalette.Highlight, QColor(76, 139, 245))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    app.setStyleSheet(
        """
        QToolTip { color: #111; background: #f2f4f8; border: 1px solid #8c95a3; }
        QDockWidget::title { padding: 6px; background: #2b3039; }
        QTabWidget::pane { border: 1px solid #3a404c; }
        QTableWidget { gridline-color: #3a404c; }
        QPushButton, QToolButton { padding: 5px 8px; }
        """
    )
