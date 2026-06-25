"""bot_status — Bot 状态查询插件。

提供 /status 命令，以图片形式展示 Bot 运行时状态、业务数据和 LLM 指标。
支持通过配置控制启用/禁用，以及自定义各状态项的默认时间窗口。
"""

from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BasePlugin, register_plugin
from src.app.plugin_system.types import PermissionLevel

from .commands.status_command import StatusCommand
from .config import BotStatusConfig

logger = get_logger("bot_status")


@register_plugin
class BotStatusPlugin(BasePlugin):
    """Bot 状态查询插件。

    注册 StatusCommand 命令组件，允许通过配置灵活控制命令权限级别，
    默认 OPERATOR 及以上权限用户可通过 /status <子命令> 查看各项指标。
    """

    plugin_name: str = "bot_status"
    plugin_description: str = (
        "通过 /status 命令查询并展示 Bot 运行时状态、业务数据和 LLM 指标"
    )
    plugin_version: str = "1.2.0"

    configs: list[type] = [BotStatusConfig]
    dependent_components: list[str] = []

    def get_components(self) -> list[type]:
        """获取插件内所有组件类。

        根据配置中的 plugin.enabled 决定是否注册命令组件，
        并根据 plugin.permission_level 动态设置命令权限级别。

        Returns:
            list[type]: 命令组件列表
        """
        cfg = self.config
        if isinstance(cfg, BotStatusConfig) and not cfg.plugin.enabled:
            logger.info("bot_status 已在配置中禁用，跳过组件注册")
            return []

        # 根据配置动态设置命令权限级别
        if isinstance(cfg, BotStatusConfig):
            perm_str = cfg.plugin.permission_level.strip().lower()
            try:
                level = PermissionLevel.from_string(perm_str)
                StatusCommand.permission_level = level
                logger.info(f"bot_status 命令权限级别已设置为: {perm_str}")
            except ValueError:
                logger.warning(
                    f"bot_status 配置中的权限级别 '{perm_str}' 无效，"
                    f"使用默认值 operator"
                )
                StatusCommand.permission_level = PermissionLevel.OPERATOR

        return [StatusCommand]