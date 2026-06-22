"""bot_status 插件配置。"""

from __future__ import annotations

from typing import ClassVar

from src.core.components.base.config import BaseConfig, Field, SectionBase, config_section


class BotStatusConfig(BaseConfig):
    """Bot Status 插件配置。"""

    config_name: ClassVar[str] = "config"
    config_description: ClassVar[str] = "Bot 状态查询插件配置"

    @config_section("plugin")
    class PluginSection(SectionBase):
        """插件开关。"""

        enabled: bool = Field(default=True, description="是否启用插件")

    @config_section("runtime")
    class RuntimeSection(SectionBase):
        """运行时状态时间窗口（运行时数据始终为实时快照，此项预留）。"""

        default_window_hours: float = Field(
            default=0,
            description="运行时状态默认时间窗口（小时，0=实时快照）",
        )

    @config_section("business")
    class BusinessSection(SectionBase):
        """业务数据默认时间窗口。"""

        default_hours: float = Field(
            default=24.0,
            description="业务数据默认统计时间窗口（小时），控制消息/流/插件等数据的回溯范围",
        )

    @config_section("llm")
    class LLMSection(SectionBase):
        """LLM 指标默认时间窗口。"""

        default_hours: float = Field(
            default=5.0,
            description="LLM 运营指标默认统计时间窗口（小时），控制 Token/成本/延迟等数据的回溯范围",
        )

    @config_section("all")
    class AllSection(SectionBase):
        """全部状态默认时间窗口。"""

        default_hours: float = Field(
            default=24.0,
            description="全部状态（/status all）默认时间窗口（小时），同时应用于业务和 LLM 数据",
        )

    @config_section("style")
    class StyleSection(SectionBase):
        """自定义界面样式（风格色盘）。"""

        bg_color: str = Field(
            default="#0d0f12",
            description="控制台底座背景颜色 (如 #0d0f12)"
        )
        border_color: str = Field(
            default="#2d3748",
            description="机架及面板边框色 (如 #2d3748)"
        )
        accent_color: str = Field(
            default="#ff9100",
            description="核心指示色/警示斜条色 (如 #ff9100)"
        )
        success_color: str = Field(
            default="#00ff66",
            description="高成功率/在线/正常填充色 (如 #00ff66)"
        )
        warning_color: str = Field(
            default="#ff9100",
            description="中成功率/警告填充色 (如 #ff9100)"
        )
        danger_color: str = Field(
            default="#ff1744",
            description="低成功率/异常填充色 (如 #ff1744)"
        )
        border_radius: str = Field(
            default="4px",
            description="机架卡片圆角，默认为 4px（提供微小圆润感）"
        )

    plugin: PluginSection = Field(default_factory=PluginSection)
    runtime: RuntimeSection = Field(default_factory=RuntimeSection)
    business: BusinessSection = Field(default_factory=BusinessSection)
    llm: LLMSection = Field(default_factory=LLMSection)
    all: AllSection = Field(default_factory=AllSection)
    style: StyleSection = Field(default_factory=StyleSection)