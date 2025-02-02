from openai import OpenAI
from typing import Optional
from dataclasses import dataclass


@dataclass
class DeepSeekConfig:
    """DeepSeek API配置"""
    api_key: str
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com"
    temperature: float = 0.7
    max_tokens: int = 1000


class DeepSeekAPI:
    def __init__(self, api_key: str, config: Optional[DeepSeekConfig] = None):
        """
        初始化DeepSeek API客户端

        Args:
            api_key: API密钥
            config: 可选的配置对象
        """
        self.config = config or DeepSeekConfig(api_key=api_key)
        self.client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )

    def process_abstract(self, abstract: str) -> str:
        """
        处理论文摘要并返回分析结果

        Args:
            abstract: 论文摘要文本

        Returns:
            str: 生成的分析文本
        """
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

            # 调用API
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.config.temperature,
                max_tokens=self.config.max_tokens,
                stream=False
            )

            # 返回生成的文本
            return response.choices[0].message.content

        except Exception as e:
            print(f"处理摘要时出错: {e}")
            raise


# 使用示例
def main():
    # 配置API
    config = DeepSeekConfig(
        api_key="",
        model="deepseek-chat",
        temperature=0.7,
        max_tokens=1000
    )

    # 创建API客户端
    api = DeepSeekAPI(config.api_key, config)

    # 测试摘要
    test_abstract = """
    This paper introduces a novel approach to transformer architecture optimization
    for natural language processing tasks. We propose several improvements to the
    attention mechanism that reduce computational complexity while maintaining or
    improving performance. Our experimental results on multiple benchmarks show a
    15% improvement in accuracy while reducing computational resources by 30%.
    The proposed method also demonstrates better generalization capabilities on
    low-resource languages.
    """

    try:
        # 处理摘要
        result = api.process_abstract(test_abstract)
        print("分析结果:")
        print(result)

    except Exception as e:
        print(f"错误: {e}")


if __name__ == "__main__":
    main()