"""
集成测试示例

集成测试用于验证多个组件协同工作的行为，
例如插件与适配器的交互、消息处理流程等。
"""

import pytest
from nonebug import App


@pytest.mark.asyncio
async def test_placeholder(app: App):
    """占位测试，确保集成测试目录可正常运行"""
