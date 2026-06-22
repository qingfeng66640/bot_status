"""bot_status — Bot 状态查询插件。

提供 /status 命令，以图片形式展示 Bot 运行时状态、业务数据和 LLM 指标。
支持通过配置控制启用/禁用，以及自定义各状态项的默认时间窗口。
"""

from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BasePlugin, register_plugin

from .commands.status_command import StatusCommand
from .config import BotStatusConfig

logger = get_logger("bot_status")


@register_plugin
class BotStatusPlugin(BasePlugin):
    """Bot 状态查询插件。

    注册 StatusCommand 命令组件，允许 OPERATOR 及以上权限用户通过
    /status <子命令> 以图片形式查看 Bot 各项运行指标。
    """

    plugin_name: str = "bot_status"
    plugin_description: str = (
        "通过 /status 命令查询并展示 Bot 运行时状态、业务数据和 LLM 指标"
    )
    plugin_version: str = "1.0.0"

    configs: list[type] = [BotStatusConfig]
    dependent_components: list[str] = []

    def get_components(self) -> list[type]:
        """获取插件内所有组件类。

        根据配置中的 plugin.enabled 决定是否注册命令组件。

        Returns:
            list[type]: 命令组件列表
        """
        cfg = self.config
        if isinstance(cfg, BotStatusConfig) and not cfg.plugin.enabled:
            logger.info("bot_status 已在配置中禁用，跳过组件注册")
            return []
        return [StatusCommand]