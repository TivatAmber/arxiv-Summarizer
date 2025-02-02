import os
import sys
from PyQt6.QtCore import QThread, pyqtSignal, QTimer
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLineEdit, QPushButton, QTextEdit,
                             QLabel, QComboBox, QSpinBox, QProgressBar, QFileDialog,
                             QMessageBox)

from arxiv_api import ArxivAPI, ArxivPaper
from deepseek_api import DeepSeekAPI
import json


class SearchWorker(QThread):
    """后台搜索线程"""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, api, search_params):
        super().__init__()
        self.api = api
        self.search_params = search_params
        self.is_running = True

    def run(self):
        try:
            if self.is_running:
                results = self.api.search(**self.search_params)
                self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))

    def stop(self):
        self.is_running = False



class AnalysisWorker(QThread):
    """后台分析线程"""
    finished = pyqtSignal(str, int)
    error = pyqtSignal(str)

    def __init__(self, api, abstract: str, paper_index: int):
        super().__init__()
        self.api = api
        self.abstract = abstract
        self.paper_index = paper_index
        self.is_running = True

    def run(self):
        try:
            if self.is_running:
                result = self.api.process_abstract(self.abstract)
                self.finished.emit(result, self.paper_index)
        except Exception as e:
            if self.is_running:
                self.error.emit(str(e))

    def stop(self):
        self.is_running = False


class DownloadWorker(QThread):
    """后台下载线程"""
    progress = pyqtSignal(int)
    finished = pyqtSignal(bool)
    error = pyqtSignal(str)

    def __init__(self, api, paper, save_path):
        super().__init__()
        self.api = api
        self.paper = paper
        self.save_path = save_path

    def run(self):
        try:
            success = self.api.download_paper(self.paper, self.save_path)
            self.finished.emit(success)
        except Exception as e:
            self.error.emit(str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.api = ArxivAPI()
        self.current_papers = []
        self.active_threads = []  # 跟踪活动线程
        self.analysis_queue = []  # 等待分析的论文队列
        self.analysis_delay = 5  # 线程间延时（秒）
        self.is_analyzing = False  # 是否正在分析
        self.config = "./config.json"

        api_key = None
        # 初始化 DeepSeek API
        if not os.path.exists(self.config):
            with open(self.config, "w") as fp:
                with open('./default_config.json', 'r') as rp:
                    fp.write(rp.read())
        else:
            api_json = json.loads(open('config.json', 'r').read())
            api_key = api_json['api_key']

        if (not api_key) or api_key == "YOUR_API_KEY":
            QMessageBox.warning(self, "警告", "未找到 DEEPSEEK_API_KEY 环境变量，论文分析功能将不可用")
        self.deepseek = DeepSeekAPI(api_key) if api_key else None

        self.init_ui()

    def closeEvent(self, event):
        """窗口关闭时的处理"""
        self.analysis_queue.clear()  # 清空分析队列
        # 停止所有活动线程
        for thread in self.active_threads:
            if hasattr(thread, 'stop'):
                thread.stop()
            thread.wait()
        event.accept()

    def init_ui(self):
        """初始化用户界面"""
        self.setWindowTitle('arXiv论文搜索器')
        self.setMinimumSize(800, 600)

        # 创建主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # 搜索区域
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText('输入搜索关键词...')
        search_button = QPushButton('搜索')
        search_button.clicked.connect(self.perform_search)

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_button)
        layout.addLayout(search_layout)

        # 高级搜索选项
        advanced_layout = QHBoxLayout()

        # 分类选择
        self.category_combo = QComboBox()
        categories = ['所有分类'] + list(ArxivAPI.get_all_categories().keys())
        self.category_combo.addItems(categories)
        advanced_layout.addWidget(QLabel('分类:'))
        advanced_layout.addWidget(self.category_combo)

        # 结果数量
        self.results_spin = QSpinBox()
        self.results_spin.setRange(1, 50)
        self.results_spin.setValue(10)
        advanced_layout.addWidget(QLabel('结果数量:'))
        advanced_layout.addWidget(self.results_spin)

        # 排序方式
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(['相关度', '最新更新', '提交时间'])
        advanced_layout.addWidget(QLabel('排序:'))
        advanced_layout.addWidget(self.sort_combo)

        advanced_layout.addStretch()
        layout.addLayout(advanced_layout)

        # 结果显示区域
        self.results_text = QTextEdit()
        self.results_text.setReadOnly(True)
        layout.addWidget(self.results_text)

        # 下载进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # 状态栏
        self.statusBar().showMessage('就绪')

    def perform_search(self):
        """执行搜索"""
        query = self.search_input.text()
        if not query:
            self.statusBar().showMessage('请输入搜索关键词')
            return

        # 准备搜索参数
        category = self.category_combo.currentText()
        if category == '所有分类':
            category = None

        sort_map = {
            '相关度': 'relevance',
            '最新更新': 'lastUpdatedDate',
            '提交时间': 'submittedDate'
        }

        search_params = {
            'query': query,
            'max_results': self.results_spin.value(),
            'sort_by': sort_map[self.sort_combo.currentText()]
        }

        if category:
            search_params['categories'] = [category]

        # 停止之前的搜索线程
        self.stop_active_threads()

        # 创建并启动新的搜索线程
        self.search_worker = SearchWorker(self.api, search_params)
        self.search_worker.finished.connect(self.handle_search_results)
        self.search_worker.error.connect(self.handle_error)
        self.active_threads.append(self.search_worker)

        self.statusBar().showMessage('正在搜索...')
        self.search_worker.start()

    def analyze_paper(self, paper: ArxivPaper, index: int):
        """分析论文摘要"""
        if not self.deepseek:
            return

        # 创建并启动分析线程
        analysis_worker = AnalysisWorker(self.deepseek, paper.abstract, index)
        analysis_worker.finished.connect(self.handle_analysis_result)
        analysis_worker.error.connect(self.handle_error)
        self.active_threads.append(analysis_worker)
        analysis_worker.start()

    def handle_analysis_result(self, result: str, paper_index: int):
        """处理分析结果"""
        self.clean_finished_threads()

        # 找到对应论文的位置
        text = self.results_text.toPlainText()
        paper_sections = text.split("=== 论文 ")

        if paper_index + 1 >= len(paper_sections):
            return

        # 更新对应论文的文本
        current_section = paper_sections[paper_index + 1]
        current_section = current_section.replace("等待分析...", "")
        current_section = current_section.replace("正在分析论文...", "")
        current_section += f"DeepSeek 分析:{result.strip()}\n\n"

        # 重建完整文本
        paper_sections[paper_index + 1] = current_section
        full_text = "=== 论文 ".join(paper_sections)
        self.results_text.setPlainText(full_text)

        # 标记当前分析完成
        self.is_analyzing = False

        # 继续处理队列中的下一篇论文
        if self.analysis_queue:
            QTimer.singleShot(self.analysis_delay * 1000, self.process_analysis_queue)

    def handle_search_results(self, papers):
        """处理搜索结果"""
        self.clean_finished_threads()
        self.current_papers = papers
        self.results_text.clear()
        self.analysis_queue.clear()  # 清空之前的分析队列

        if not papers:
            self.results_text.append('未找到相关论文')
            self.statusBar().showMessage('搜索完成: 未找到结果')
            return

        for i, paper in enumerate(papers, 1):
            self.results_text.append(f"=== 论文 {i} ===")
            self.results_text.append(f"标题: {paper.title}")
            self.results_text.append(f"作者: {', '.join(paper.authors)}")
            self.results_text.append(f"摘要: {paper.abstract[:300]}...")
            self.results_text.append(f"分类: {', '.join(paper.categories)}")
            self.results_text.append(f"发布日期: {paper.published_date}")
            self.results_text.append(f"arXiv ID: {paper.paper_id}")
            self.results_text.append(f"PDF链接: {paper.pdf_url}")
            self.results_text.append(f"arXiv链接: {paper.arxiv_url}")

            # 将论文添加到分析队列
            if self.deepseek:
                self.analysis_queue.append((paper, i - 1))
                self.results_text.append("等待分析...")

        self.statusBar().showMessage(f'搜索完成: 找到 {len(papers)} 篇论文')

        # 开始处理分析队列
        if self.deepseek and not self.is_analyzing:
            self.process_analysis_queue()

    def process_analysis_queue(self):
        """处理分析队列"""
        if not self.analysis_queue or self.is_analyzing:
            return

        self.is_analyzing = True
        paper, index = self.analysis_queue.pop(0)
        self.analyze_paper(paper, index)

        # 如果队列中还有论文，设置定时器处理下一个
        if self.analysis_queue:
            QTimer.singleShot(self.analysis_delay * 1000, self.process_analysis_queue)

    def handle_error(self, error_msg):
        """处理错误"""
        # 清理已完成的线程
        self.clean_finished_threads()

        self.statusBar().showMessage(f'发生错误: {error_msg}')
        QMessageBox.warning(self, "错误", f"处理过程中出现错误：{error_msg}")

    def download_paper(self, paper):
        """下载论文"""
        file_name = f"{paper.paper_id}.pdf"
        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "保存PDF",
            file_name,
            "PDF文件 (*.pdf)"
        )

        if save_path:
            self.progress_bar.show()
            self.progress_bar.setValue(0)

            # 创建并启动下载线程
            self.download_worker = DownloadWorker(
                self.api,
                paper,
                save_path
            )
            self.download_worker.finished.connect(self.handle_download_finished)
            self.download_worker.error.connect(self.handle_error)
            self.download_worker.progress.connect(self.progress_bar.setValue)

            self.statusBar().showMessage('正在下载...')
            self.download_worker.start()

    def handle_download_finished(self, success):
        """处理下载完成"""
        self.progress_bar.hide()
        if success:
            self.statusBar().showMessage('下载完成')
        else:
            self.statusBar().showMessage('下载失败')

    def stop_active_threads(self):
        """停止所有活动线程"""
        for thread in self.active_threads:
            if hasattr(thread, 'stop'):
                thread.stop()
            if thread.isRunning():
                thread.wait()
        self.active_threads.clear()

    def clean_finished_threads(self):
        """清理已完成的线程"""
        self.active_threads = [thread for thread in self.active_threads if thread.isRunning()]


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()