import json
import os
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLineEdit, QPushButton, QLabel, QComboBox, QSpinBox, QProgressBar,
                             QFileDialog,
                             QMessageBox, QTabWidget)
from arxiv_api import ArxivAPI, ArxivPaper
from deepseek_api import DeepSeekAPI
from paper_tab import PaperTab
from workers import SearchWorker, AnalysisWorker, DownloadWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.api = ArxivAPI()
        self.current_papers = []
        self.active_threads = []  # 跟踪活动线程
        self.analysis_queue = []  # 等待分析的论文队列
        self.analysis_delay = 3  # 线程间延时（秒）
        self.is_analyzing = False  # 是否正在分析
        self.config = "./config.json"
        self.download_buttons = []  # 存储下载按钮的列表
        self.download_layout = None  # 用于存储下载按钮的布局引用
        self.paper_tabs = {}  # 存储论文标签页的字典
        self.search_in_progress = False  # 添加搜索状态标志

        api_key = None
        # 初始化 DeepSeek API
        if not os.path.exists(self.config):
            with open(self.config, "w") as fp:
                with open('./default_config.json', 'r') as rp:
                    fp.write(rp.read())
        else:
            api_json = json.loads(open('config.json', 'r').read())
            api_key = api_json['api_key']['deepseek']

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
        self.results_spin.setRange(1, 10)
        self.results_spin.setValue(3)
        advanced_layout.addWidget(QLabel('结果数量:'))
        advanced_layout.addWidget(self.results_spin)

        # 排序方式
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(['相关度', '最新更新', '提交时间'])
        advanced_layout.addWidget(QLabel('排序:'))
        advanced_layout.addWidget(self.sort_combo)

        advanced_layout.addStretch()
        layout.addLayout(advanced_layout)

        # 创建水平布局来容纳标签页和下载按钮
        content_layout = QHBoxLayout()

        # 创建标签页控件
        self.tab_widget = QTabWidget()
        content_layout.addWidget(self.tab_widget, stretch=4)

        # 创建下载按钮区域
        download_widget = QWidget()
        self.download_layout = QVBoxLayout(download_widget)
        content_layout.addWidget(download_widget, stretch=1)

        # 将内容布局添加到主布局
        layout.addLayout(content_layout)

        # 下载进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)

        # 状态栏
        self.statusBar().showMessage('就绪')

    def perform_search(self):
        """执行搜索"""
        if self.search_in_progress:
            self.statusBar().showMessage('搜索正在进行中，请稍候...')
            return

        query = self.search_input.text()
        if not query:
            self.statusBar().showMessage('请输入搜索关键词')
            return

        # 标记搜索开始
        self.search_in_progress = True

        # 停止所有活动线程并清理资源
        self.cleanup_before_search()

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
        try:
            # 移除已完成的分析请求
            if self.analysis_queue and self.analysis_queue[0][1] == paper_index:
                self.analysis_queue.pop(0)

            # 更新UI
            if paper_index in self.paper_tabs:
                paper_tab = self.paper_tabs[paper_index]
                paper_tab.analysis_text.setPlainText(result.strip())

            # 清理已完成的线程
            self.clean_finished_threads()

        finally:
            # 重置分析状态
            self.is_analyzing = False

            # 如果队列中还有论文,设置定时器处理下一个
            if self.analysis_queue:
                QTimer.singleShot(self.analysis_delay * 1000, self.process_analysis_queue)

    def handle_search_results(self, papers):
        """处理搜索结果"""
        try:
            self.clean_finished_threads()
            self.current_papers = papers

            if not papers:
                # 显示无结果的标签页
                no_results = QWidget()
                layout = QVBoxLayout(no_results)
                layout.addWidget(QLabel('未找到相关论文'))
                self.tab_widget.addTab(no_results, '搜索结果')
                self.statusBar().showMessage('搜索完成: 未找到结果')
                return

            # 为每篇论文创建标签页
            for i, paper in enumerate(papers, 1):
                # 创建论文标签页
                paper_tab = PaperTab(paper)
                tab_title = f"论文 {i}: {paper.title[:20]}..."
                self.tab_widget.addTab(paper_tab, tab_title)
                self.paper_tabs[i-1] = paper_tab

                # 创建下载按钮
                download_btn = QPushButton(f'下载论文 {i}')
                download_btn.setFixedWidth(100)
                download_btn.clicked.connect(lambda checked, p=paper: self.download_paper(p))
                self.download_buttons.append(download_btn)
                self.download_layout.addWidget(download_btn)

                # 将论文添加到分析队列
                if self.deepseek:
                    self.analysis_queue.append((paper, i - 1))

            # 添加弹性空间到下载按钮布局底部
            self.download_layout.addStretch()

            self.statusBar().showMessage(f'搜索完成: 找到 {len(papers)} 篇论文')

            # 开始处理分析队列
            if self.deepseek and not self.is_analyzing:
                QTimer.singleShot(100, self.process_analysis_queue)

        finally:
            # 重置搜索状态
            self.search_in_progress = False

    def process_analysis_queue(self):
        """处理分析队列"""
        # 如果已经在分析或队列为空,直接返回
        if not self.analysis_queue or self.is_analyzing:
            return

        # 设置分析状态
        self.is_analyzing = True

        try:
            paper, index = self.analysis_queue[0]  # 只查看队列头部,暂时不移除

            # 确保索引有效且UI组件存在
            if index not in self.paper_tabs:
                self.analysis_queue.pop(0)  # 移除无效的分析请求
                self.is_analyzing = False
                return

            # 更新UI显示分析状态
            paper_tab = self.paper_tabs[index]
            paper_tab.analysis_text.setPlainText("正在分析论文...")

            # 创建并配置分析线程
            analysis_worker = AnalysisWorker(self.deepseek, paper.abstract, index)
            analysis_worker.finished.connect(self.handle_analysis_result)
            analysis_worker.error.connect(self.handle_analysis_error)

            # 将线程添加到活动线程列表
            self.active_threads.append(analysis_worker)

            # 启动线程
            analysis_worker.start()

        except Exception as e:
            # 发生错误时确保状态被重置
            self.is_analyzing = False
            self.statusBar().showMessage(f'分析过程出错: {str(e)}')

    def handle_error(self, error_msg):
        """处理错误"""
        # 清理已完成的线程
        self.clean_finished_threads()

        self.statusBar().showMessage(f'发生错误: {error_msg}')
        QMessageBox.warning(self, "错误", f"处理过程中出现错误：{error_msg}")

    def handle_analysis_error(self, error_msg: str):
        """处理分析错误"""
        try:
            # 移除导致错误的分析请求
            if self.analysis_queue:
                self.analysis_queue.pop(0)

            self.statusBar().showMessage(f'分析出错: {error_msg}')

        finally:
            # 重置分析状态
            self.is_analyzing = False

            # 尝试处理队列中的下一个请求
            if self.analysis_queue:
                QTimer.singleShot(self.analysis_delay * 1000, self.process_analysis_queue)

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

    def cleanup_before_search(self):
        """在开始新搜索前清理资源"""
        # 确保所有分析线程都被正确停止
        for thread in self.active_threads:
            if isinstance(thread, AnalysisWorker):
                thread.stop()

        # 等待所有线程完成
        for thread in self.active_threads:
            if thread.isRunning():
                thread.wait()

        # 清空线程列表
        self.active_threads.clear()

        # 清空分析队列
        self.analysis_queue.clear()

        # 重置分析状态
        self.is_analyzing = False

        # 清理UI元素
        self.tab_widget.clear()
        self.paper_tabs.clear()

        # 清理下载按钮
        for btn in self.download_buttons:
            btn.deleteLater()
        self.download_buttons.clear()

        if self.download_layout:
            while self.download_layout.count():
                item = self.download_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

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