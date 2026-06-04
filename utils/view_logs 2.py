

import json
import os
import sys
from pathlib import Path

import markdown2
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QFont
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QTextBrowser, QLabel,
    QStackedWidget, QFileDialog, QTreeWidget, QTreeWidgetItem, QMenu, QAction, QTreeWidgetItemIterator
)


MARKDOWN_FONT_SIZE = 24  
JSON_EXPAND_LEVEL = 3  


class FilePreviewer(QWidget):
    def __init__(self, folder_path=None):
        super().__init__()
        if folder_path is None:
            default_path = os.path.join(Path(__file__).parent.parent, "logs")
            if not os.path.isdir(default_path):
                default_path = ''
            self.folder_path = QFileDialog.getExistingDirectory(None, "", default_path)
            if self.folder_path == '':
                sys.exit(0)
        else:
            self.folder_path = folder_path
        self.init_ui()
        self.load_files()

    def init_ui(self):
       
        self.setWindowTitle("")
        self.showMaximized()  

        main_layout = QHBoxLayout(self)

        
        self.file_list = QListWidget()
        self.file_list.setFixedWidth(400)  
        self.file_list.itemClicked.connect(self.display_file)
        self.file_list.currentRowChanged.connect(self.update_preview)  
        main_layout.addWidget(self.file_list)

        
        self.preview_stack = QStackedWidget()

        
        self.text_view = QTextBrowser()
        self.text_view.setOpenExternalLinks(True)  
        self.text_view.setStyleSheet(f"font-size: {MARKDOWN_FONT_SIZE}px;")  
        self.preview_stack.addWidget(self.text_view)

        
        image_container = QWidget()
        image_layout = QVBoxLayout(image_container)

        
        self.image_info = QLabel(" ")
        self.image_info.setAlignment(Qt.AlignRight)
        self.image_info.setFont(QFont("Arial", 10))
        image_layout.addWidget(self.image_info)

        
        self.image_view = QLabel(alignment=Qt.AlignCenter)
        image_layout.addWidget(self.image_view)
        self.preview_stack.addWidget(image_container)

        
        self.json_view = QTreeWidget()
        self.json_view.setHeaderLabels(["Key", "Value"])  
        self.json_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.json_view.customContextMenuRequested.connect(self.show_json_menu)  
        self.preview_stack.addWidget(self.json_view)

        main_layout.addWidget(self.preview_stack)

    def load_files(self):
        
        if not os.path.exists(self.folder_path):
            return

        files = os.listdir(self.folder_path)

        
        def extract_number(filename):
            index = filename.split('.', 2)
            return int(index[0]), int(index[1])

        files = sorted(files, key=extract_number)

        
        for file in files:
            self.file_list.addItem(file)

    def display_file(self, item):
        
        file_path = os.path.join(self.folder_path, item.text())

        if file_path.endswith((".md", ".txt")):
            self.show_text(file_path)
        elif file_path.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
            self.show_image(file_path)
        elif file_path.endswith(".json"):
            self.show_json(file_path)
        else:
            self.text_view.setText("")
            self.preview_stack.setCurrentWidget(self.text_view)

    def update_preview(self, row):
        
        item = self.file_list.item(row)
        if item:
            self.display_file(item)

    def show_text(self, file_path):
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if file_path.endswith(".md"):
            
            content = markdown2.markdown(content)
        self.text_view.setHtml(content)
        self.preview_stack.setCurrentWidget(self.text_view)

    def show_image(self, file_path):
       
        pixmap = QPixmap(file_path)
        original_size = pixmap.size()

        self.image_info.setText(f": {original_size.width()} x {original_size.height()}")
        scaled_pixmap = pixmap.scaled(self.image_view.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_view.setPixmap(scaled_pixmap)

        self.preview_stack.setCurrentWidget(self.image_view.parent())

    def show_json(self, file_path):
        
        self.json_view.clear()  
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.populate_json_tree(self.json_view, data, level=0) 
        except Exception as e:
            error_item = QTreeWidgetItem(["", str(e)])
            self.json_view.addTopLevelItem(error_item)

        self.preview_stack.setCurrentWidget(self.json_view)

    def populate_json_tree(self, parent, data, level):
        
        if not isinstance(data, (dict, list)):
            return
        data_iter = data.items() if isinstance(data, dict) else enumerate(data)
        for key, value in data_iter:
            item = QTreeWidgetItem([str(key), '' if isinstance(value, (dict, list)) else str(value)])
            parent.addTopLevelItem(item) if isinstance(parent, QTreeWidget) else parent.addChild(item)
            self.populate_json_tree(item, value, level + 1)
            item.setExpanded(level < JSON_EXPAND_LEVEL)

    def show_json_menu(self, position):
        
        menu = QMenu()
        expand_action = QAction("", self)
        collapse_action = QAction("", self)

        expand_action.triggered.connect(lambda: self.expand_tree(self.json_view, True))
        collapse_action.triggered.connect(lambda: self.expand_tree(self.json_view, False))

        menu.addAction(expand_action)
        menu.addAction(collapse_action)
        menu.exec_(self.json_view.viewport().mapToGlobal(position))

    def expand_tree(self, tree, expand=True):
        
        iterator = QTreeWidgetItemIterator(tree)
        while iterator.value():
            iterator.value().setExpanded(expand)
            iterator += 1


def view_folder():
    app = QApplication(sys.argv)
    viewer = FilePreviewer()
    viewer.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    view_folder()
