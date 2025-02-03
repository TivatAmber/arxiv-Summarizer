from openai import OpenAI
from typing import Optional, Tuple
from dataclasses import dataclass
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Event


@dataclass
class DeepSeekConfig:
    """DeepSeek API配置"""
    api_key: str
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.7
    max_tokens: int = 1000
    timeout: float = 180.0  # 设置默认超时时间为180秒
    check_interval: float = 2.0  # 状态检查间隔时间


class RequestStatus:
    """请求状态跟踪器"""
    def __init__(self):
        self.start_time = time.time()
        self.last_check = self.start_time
        self.is_completed = False
        self.has_error = False
        self.error_message = None
        self.result = None
        self._stop_event = Event()

    def elapsed_time(self) -> float:
        """返回已经过的时间（秒）"""
        return time.time() - self.start_time

    def should_stop(self) -> bool:
        """检查是否应该停止请求"""
        return self._stop_event.is_set()

    def stop(self):
        """标记应该停止请求"""
        self._stop_event.set()


class DeepSeekAPI:
    def __init__(self, api_key: str, config: Optional[DeepSeekConfig] = None):
        """初始化DeepSeek API客户端"""
        self.config = config or DeepSeekConfig(api_key=api_key)
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url,
            timeout=self.config.timeout  # 设置OpenAI客户端的超时时间
        )
        self.executor = ThreadPoolExecutor(max_workers=1)

    def process_abstract(self, abstract: str, status_callback=None) -> str:
        """
        处理论文摘要并返回分析结果

        Args:
            abstract: 论文摘要文本
            status_callback: 可选的状态回调函数，用于报告进度

        Returns:
            str: 生成的分析文本

        Raises:
            TimeoutError: 如果请求超过配置的超时时间
            Exception: 其他可能的错误
        """
        # 创建请求状态跟踪器
        status = RequestStatus()

        try:
            # 在后台线程中执行API调用
            future = self.executor.submit(
                self._make_api_call,
                abstract,
                status,
                status_callback
            )

            # 在主线程中等待结果，同时检查状态
            while not future.done():
                # 检查是否超时
                if status.elapsed_time() > self.config.timeout:
                    status.stop()  # 标记应该停止
                    raise TimeoutError(f"请求超时（{self.config.timeout}秒）")

                # 如果提供了回调函数，定期报告状态
                if status_callback and (time.time() - status.last_check) >= self.config.check_interval:
                    status_callback(f"正在等待响应... （已用时：{status.elapsed_time():.1f}秒）")
                    status.last_check = time.time()

                # 短暂休眠以避免密集循环
                time.sleep(0.1)

            # 获取结果
            result = future.result()
            if status_callback:
                status_callback("分析完成")
            return result

        except TimeoutError as e:
            if status_callback:
                status_callback(f"请求超时: {str(e)}")
            raise

        except Exception as e:
            if status_callback:
                status_callback(f"发生错误: {str(e)}")
            raise

    def _make_api_call(self, abstract: str, status: RequestStatus, status_callback=None) -> str:
        """实际执行API调用的内部方法"""
        try:
            # 构建提示词
            system_prompt = """你是一个专业的学术论文分析助手。请分析给定的论文摘要，并从以下几个方面进行总结：
            1. 研究问题和目标
            2. 主要方法和技术
            3. 关键发现和结果
            4. 创新点和贡献
            5. 潜在的应用价值

            请用简洁专业的语言进行分析。"""

            user_prompt = f"请分析以下论文摘要：\n\n{abstract}"

            # 定期检查是否应该停止
            if status.should_stop():
                raise InterruptedError("请求被取消")

            # 调用API
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=False  # 不使用流式传输，因为我们需要完整的响应
            )

            # 再次检查是否应该停止
            if status.should_stop():
                raise InterruptedError("请求被取消")

            # 返回生成的文本
            return response.choices[0].message.content

        except Exception as e:
            status.has_error = True
            status.error_message = str(e)
            raise