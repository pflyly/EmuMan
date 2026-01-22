import sys
from PySide6.QtCore import Qt, qInstallMessageHandler
from PySide6.QtWidgets import QApplication

from app.utils.logger import setup_logging, handle_exception
from app.ui.main_window import MainWindow

if __name__ == '__main__':
    setup_logging()
    
    # Suppress specific Qt warnings
    def simple_qt_handler(mode, context, message):
        if "QFont::setPointSize: Point size <= 0" in message:
            return
        sys.stderr.write(f"{message}\n")
        
    qInstallMessageHandler(simple_qt_handler)

    sys.excepthook = handle_exception
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    app.exec()
