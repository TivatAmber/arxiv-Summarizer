import requests
import xmltodict
import json
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import time
from PyQt6.QtCore import QObject, pyqtSignal


@dataclass
class ArxivPaper:
    """论文数据类"""
    title: str
    abstract: str
    authors: List[str]
    paper_id: str
    pdf_url: str
    published_date: str
    updated_date: str
    categories: List[str]
    primary_category: str
    arxiv_url: str

    @classmethod
    def from_api_response(cls, entry: Dict) -> 'ArxivPaper':
        """从API响应创建论文对象"""
        # 处理作者信息
        if isinstance(entry.get('author', []), list):
            authors = [author['name'] for author in entry['author']]
        else:
            authors = [entry['author']['name']]

        # 处理分类信息
        if isinstance(entry.get('category', []), list):
            categories = [cat['@term'] for cat in entry['category']]
        else:
            categories = [entry['category']['@term']] if entry.get('category') else []

        # 获取PDF和arXiv链接
        pdf_url = next((link['@href'] for link in entry['link'] if link.get('@title') == 'pdf'), '')
        arxiv_url = next((link['@href'] for link in entry['link'] if link.get('@title') is None), '')

        return cls(
            title=entry['title'].replace('\n', ' ').strip(),
            abstract=entry['summary'].replace('\n', ' ').strip(),
            authors=authors,
            paper_id=entry['id'].split('/abs/')[-1],
            pdf_url=pdf_url,
            published_date=entry['published'],
            updated_date=entry['updated'],
            categories=categories,
            primary_category=categories[0] if categories else '',
            arxiv_url=arxiv_url
        )


class ArxivAPI(QObject):
    """arXiv API客户端类"""
    # 定义信号
    search_started = pyqtSignal()
    search_finished = pyqtSignal(list)  # 发送搜索结果列表
    search_error = pyqtSignal(str)  # 发送错误信息
    download_progress = pyqtSignal(int)  # 发送下载进度
    download_finished = pyqtSignal(str)  # 发送保存路径
    download_error = pyqtSignal(str)  # 发送下载错误信息

    def __init__(self):
        super().__init__()
        self.base_url = "http://export.arxiv.org/api/query"
        self.last_request_time = 0
        self.min_request_interval = 3  # 最小请求间隔(秒)

    def _wait_for_rate_limit(self):
        """等待以遵守速率限制"""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.min_request_interval:
            time.sleep(self.min_request_interval - elapsed)
        self.last_request_time = time.time()

    def search(
            self,
            query: str,
            start: int = 0,
            max_results: int = 10,
            sort_by: str = 'relevance',
            sort_order: str = 'descending',
            categories: Optional[List[str]] = None
    ) -> List[ArxivPaper]:
        """
        搜索arXiv论文

        参数:
            query (str): 搜索关键词
            start (int): 起始位置
            max_results (int): 返回结果数量
            sort_by (str): 排序方式 ('relevance', 'lastUpdatedDate', 'submittedDate')
            sort_order (str): 排序顺序 ('ascending', 'descending')
            categories (List[str]): 限制搜索的分类列表

        返回:
            List[ArxivPaper]: 论文对象列表
        """
        self.search_started.emit()

        try:
            # 构建查询
            search_query = query
            if categories:
                cat_query = ' OR '.join(f'cat:{cat}' for cat in categories)
                search_query = f'({search_query}) AND ({cat_query})'

            # 构建参数
            params = {
                'search_query': search_query,
                'start': start,
                'max_results': min(max_results, 50),  # arXiv限制
                'sortBy': sort_by,
                'sortOrder': sort_order
            }

            # 等待速率限制
            self._wait_for_rate_limit()

            # 发送请求
            response = requests.get(self.base_url, params=params)
            response.raise_for_status()

            # 解析响应
            data = xmltodict.parse(response.text)
            entries = data['feed'].get('entry', [])

            # 确保entries是列表
            if not isinstance(entries, list):
                entries = [entries]

            # 转换为论文对象
            papers = [ArxivPaper.from_api_response(entry) for entry in entries]

            self.search_finished.emit(papers)
            return papers

        except Exception as e:
            error_msg = f"搜索出错: {str(e)}"
            self.search_error.emit(error_msg)
            return []

    def download_paper(self, paper: ArxivPaper, save_path: str) -> bool:
        """
        下载论文PDF

        参数:
            paper (ArxivPaper): 论文对象
            save_path (str): 保存路径

        返回:
            bool: 下载是否成功
        """
        try:
            response = requests.get(paper.pdf_url, stream=True)
            response.raise_for_status()

            # 获取文件大小
            total_size = int(response.headers.get('content-length', 0))
            block_size = 8192
            downloaded = 0

            with open(save_path, 'wb') as f:
                for data in response.iter_content(block_size):
                    downloaded += len(data)
                    f.write(data)

                    if total_size:
                        progress = int((downloaded / total_size) * 100)
                        self.download_progress.emit(progress)

            self.download_finished.emit(save_path)
            return True

        except Exception as e:
            error_msg = f"下载出错: {str(e)}"
            self.download_error.emit(error_msg)
            return False

    def advanced_search(
            self,
            title: Optional[str] = None,
            abstract: Optional[str] = None,
            author: Optional[str] = None,
            categories: Optional[List[str]] = None,
            date_from: Optional[str] = None,
            date_to: Optional[str] = None,
            **kwargs
    ) -> List[ArxivPaper]:
        """
        高级搜索

        参数:
            title (str): 标题关键词
            abstract (str): 摘要关键词
            author (str): 作者名
            categories (List[str]): 分类列表
            date_from (str): 起始日期 (YYYY-MM-DD)
            date_to (str): 结束日期 (YYYY-MM-DD)
        """
        query_parts = []

        if title:
            query_parts.append(f'ti:"{title}"')
        if abstract:
            query_parts.append(f'abs:"{abstract}"')
        if author:
            query_parts.append(f'au:"{author}"')
        if date_from or date_to:
            date_query = f'submittedDate:[{date_from or "*"} TO {date_to or "now"}]'
            query_parts.append(date_query)

        query = ' AND '.join(query_parts) if query_parts else '*:*'

        return self.search(query, categories=categories, **kwargs)

    @staticmethod
    def get_all_categories() -> Dict[str, str]:
        """
        获取所有可用的arXiv分类

        返回:
            Dict[str, str]: 分类代码到描述的映射
        """
        return {
            'cs.AI': '人工智能',
            'cs.CL': '计算语言学',
            'cs.CV': '计算机视觉',
            'cs.LG': '机器学习',
            'cs.NE': '神经网络',
            'stat.ML': '机器学习(统计)',
            'math.OC': '优化和控制',
            # ... 可以添加更多分类
        }


# 使用示例
def main():
    api = ArxivAPI()

    # 连接信号
    api.search_started.connect(lambda: print("开始搜索..."))
    api.search_finished.connect(lambda papers: print(f"找到 {len(papers)} 篇论文"))
    api.search_error.connect(lambda err: print(f"错误: {err}"))

    # 基本搜索
    papers = api.search("deep learning", max_results=2)
    for paper in papers:
        print(f"标题: {paper.title}")
        print(f"作者: {', '.join(paper.authors)}")
        print(f"摘要: {paper.abstract[:200]}...")
        print("-" * 80)

    # 高级搜索
    papers = api.advanced_search(
        title="transformer",
        categories=['cs.AI', 'cs.CL'],
        date_from="2023-01-01",
        max_results=2
    )


if __name__ == '__main__':
    main()