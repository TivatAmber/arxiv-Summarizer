from PyQt6.QtCore import QThread, pyqtSignal


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
    status_update = pyqtSignal(str)  # 新增状态更新信号

    def __init__(self, api, abstract: str, paper_index: int):
        super().__init__()
        self.api = api
        self.abstract = abstract
        self.paper_index = paper_index
        self._is_running = True

    def status_callback(self, message: str):
        """处理API的状态更新"""
        if self._is_running:
            self.status_update.emit(message)

    def run(self):
        try:
            if self._is_running and self.api:
                # 使用状态回调处理API调用
                result = self.api.process_abstract(
                    self.abstract,
                    status_callback=self.status_callback
                )
                if self._is_running:
                    self.finished.emit(result, self.paper_index)
        except TimeoutError as e:
            if self._is_running:
                self.error.emit(f"分析超时: {str(e)}")
        except Exception as e:
            if self._is_running:
                self.error.emit(str(e))

    def stop(self):
        """安全地停止线程"""
        self._is_running = False
        self.wait()


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