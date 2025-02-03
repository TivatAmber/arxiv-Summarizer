from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QGridLayout, QTextEdit, QLabel

from arxiv_api import ArxivPaper


class PaperTab(QWidget):
    """单个论文的标签页类"""

    def __init__(self, paper: ArxivPaper, parent=None):
        super().__init__(parent)
        self.paper = paper
        self.init_ui()

    def init_ui(self):
        """初始化标签页界面"""
        layout = QVBoxLayout(self)

        # 创建一个滚动区域来容纳所有内容
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)

        # 使用网格布局来展示论文信息
        grid = QGridLayout()

        # 添加论文详细信息
        labels = [
            ("标题:", self.paper.title),
            ("作者:", ", ".join(self.paper.authors)),
            ("分类:", ", ".join(self.paper.categories)),
            ("发布日期:", self.paper.published_date),
            ("arXiv ID:", self.paper.paper_id),
            ("PDF链接:", self.paper.pdf_url),
            ("arXiv链接:", self.paper.arxiv_url)
        ]

        for i, (label, value) in enumerate(labels):
            # 创建标签
            label_widget = QLabel(label)
            label_widget.setStyleSheet("font-weight: bold;")

            # 创建值的文本框
            if label == "摘要:":
                value_widget = QTextEdit()
                value_widget.setReadOnly(True)
                value_widget.setMaximumHeight(100)
                value_widget.setPlainText(value)
            else:
                value_widget = QLabel(value)
                value_widget.setWordWrap(True)
                value_widget.setTextInteractionFlags(
                    Qt.TextInteractionFlag.TextSelectableByMouse |
                    Qt.TextInteractionFlag.TextBrowserInteraction
                )

            grid.addWidget(label_widget, i, 0)
            grid.addWidget(value_widget, i, 1)

        # 添加摘要（使用文本编辑框以支持更长的文本）
        abstract_label = QLabel("摘要:")
        abstract_label.setStyleSheet("font-weight: bold;")
        abstract_text = QTextEdit()
        abstract_text.setPlainText(self.paper.abstract)
        abstract_text.setReadOnly(True)
        abstract_text.setMinimumHeight(100)  # 为摘要设置最小高度

        grid.addWidget(abstract_label, len(labels), 0)
        grid.addWidget(abstract_text, len(labels), 1)

        # 设置第二列（值）的拉伸因子
        grid.setColumnStretch(1, 1)

        # 将网格布局添加到内容布局中
        content_layout.addLayout(grid)

        # 为DeepSeek分析预留位置
        self.analysis_text = QTextEdit()
        self.analysis_text.setReadOnly(True)
        self.analysis_text.setPlaceholderText("等待分析...")
        self.analysis_text.setMinimumHeight(100)

        analysis_label = QLabel("DeepSeek 分析:")
        analysis_label.setStyleSheet("font-weight: bold;")
        content_layout.addWidget(analysis_label)
        content_layout.addWidget(self.analysis_text)

        # 添加一些底部的空间
        content_layout.addStretch()

        # 设置滚动区域的内容
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)
