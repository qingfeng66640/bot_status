"""bot_status 状态查询命令。

提供 /status 命令，以图片形式展示 Bot 运行时状态、业务数据和 LLM 指标。

支持的子命令（中英文均可）：
    /status                     — 显示全部状态
    /status runtime / 运行       — 运行时状态
    /status business / 业务 [h]  — 业务数据，可选小时数
    /status llm [h]             — LLM 指标，可选小时数
    /status all / 全部 [h]      — 全部状态，可选小时数
"""
from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.send_api import send_image
from src.app.plugin_system.base import BaseCommand, cmd_route
from src.app.plugin_system.types import PermissionLevel

from ..managers.status_manager import get_status_manager
from ..utils.image_renderer import BrowserNotAvailableError, ImageRenderer

logger = get_logger("bot_status.command")


class StatusCommand(BaseCommand):
    """Bot 状态查询命令（OPERATOR 及以上可用）。"""

    command_name: str = "status"
    command_description: str = "查询 Bot 状态信息并以图片展示（运行时/业务/LLM），支持指定时间窗口"
    permission_level: PermissionLevel = PermissionLevel.OPERATOR

    @classmethod
    def match(cls, parts: list[str]) -> int:
        if not parts:
            return 0
        if parts[0] in ("status", "状态"):
            return 1
        return 0

    # ------------------------------------------------------------------
    # 配置辅助
    # ------------------------------------------------------------------

    @property
    def _cfg(self):
        """获取插件配置实例。"""
        return self.plugin.config if self.plugin else None

    def _config_hours(self, section: str) -> float | None:
        """从配置读取某 section 的 default_hours。"""
        cfg = self._cfg
        if cfg is None:
            return None
        sec = getattr(cfg, section, None)
        if sec is None:
            return None
        val = getattr(sec, "default_hours", None)
        return float(val) if val else None

    def _resolve_hours(self, hours_arg: float | None, section: str) -> float | None:
        """解析时间窗口：命令参数 > 配置文件 > None（使用默认行为）。"""
        if hours_arg is not None and hours_arg > 0:
            return float(hours_arg)
        return self._config_hours(section)

    # ------------------------------------------------------------------
    # 渲染 & 发送
    # ------------------------------------------------------------------

    async def _render_and_send(self, title: str, sections: list[dict]) -> tuple[bool, str]:
        try:
            renderer = ImageRenderer()
            # 获取用户配置的 style
            style_dict = {}
            custom_html_path = ""
            chromium_cache_path = ""
            cfg = self._cfg
            if cfg is not None and getattr(cfg, "style", None) is not None:
                style_dict = {
                    "bg_color": cfg.style.bg_color,
                    "border_color": cfg.style.border_color,
                    "accent_color": cfg.style.accent_color,
                    "success_color": cfg.style.success_color,
                    "warning_color": cfg.style.warning_color,
                    "danger_color": cfg.style.danger_color,
                    "border_radius": cfg.style.border_radius,
                }
                custom_html_path = getattr(cfg.style, "custom_html_path", "")
                chromium_cache_path = getattr(cfg.style, "chromium_cache_path", "")
            image_base64 = await renderer.render_to_base64(
                title, sections, style=style_dict, custom_template_path=custom_html_path,
                chromium_cache_path=chromium_cache_path,
            )
            success = await send_image(image_base64, stream_id=self.stream_id)
            return (True, "ok") if success else (False, "send_failed")
        except BrowserNotAvailableError as e:
            logger.warning(f"Chromium 浏览器未就绪: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"渲染或发送状态图片失败: {e}", exc_info=True)
            return False, str(e)

    # ------------------------------------------------------------------
    # 运行时
    # ------------------------------------------------------------------

    @cmd_route()
    async def _handle_default(self) -> tuple[bool, str]:
        """默认路由（无子命令时触发），展示全部状态。"""
        return await self.handle_all()

    async def execute(self, message_text: str = "") -> tuple[bool, str]:
        """执行命令的入口点（mpdt 组件检查要求），委托父类进行路由分发。"""
        return await super().execute(message_text)

    @cmd_route("runtime")
    async def handle_runtime(self) -> tuple[bool, str]:
        mgr = get_status_manager()
        d = mgr.get_runtime_status()

        sections = [
            {
                "title": "适配器",
                "rows": [
                    ("在线适配器", d["adapter"]["active_count"]),
                    ("适配器签名", d["adapter"]["active_signatures"]),
                ],
            },
            {
                "title": "调度器",
                "rows": [
                    ("调度器状态", d["scheduler"]["is_running"]),
                    ("运行时长 (秒)", int(d["scheduler"]["uptime_seconds"])),
                    ("调度任务总数", d["scheduler"]["total_tasks"]),
                    ("正在运行", d["scheduler"]["running_tasks"]),
                    ("调度成功率", d["scheduler"]["success_rate"] * 100),
                ],
            },
            {
                "title": "任务管理器",
                "rows": [
                    ("任务总数", d["task"]["total_tasks"]),
                    ("活跃任务", d["task"]["active_tasks"]),
                    ("后台守护", d["task"]["daemon_tasks"]),
                    ("任务分组数", d["task"]["groups"]),
                ],
            },
            {
                "title": "事件系统",
                "rows": [
                    ("事件处理器", d["event"]["handler_count"]),
                    ("临时处理器", d["event"]["temporary_handler_count"]),
                    ("事件类型", d["event"]["event_type_count"]),
                    ("总订阅数", d["event"]["total_subscriptions"]),
                ],
            },
        ]
        return await self._render_and_send("Bot 运行时状态", sections)

    @cmd_route("运行")
    async def handle_runtime_cn(self) -> tuple[bool, str]:
        return await self.handle_runtime()

    # ------------------------------------------------------------------
    # 业务数据
    # ------------------------------------------------------------------

    @cmd_route("business")
    async def handle_business(self, hours: float = 0.0) -> tuple[bool, str]:
        h = self._resolve_hours(hours if hours > 0 else None, "business")
        mgr = get_status_manager()
        d = await mgr.get_business_status(hours=h)
        period = d["messages"].get("period_label", f"{h:.0f}h" if h else "今日")

        sections = [
            {
                "title": f"消息统计 · {period}",
                "rows": [
                    ("消息总数", d["messages"]["total"]),
                    ("入站消息", d["messages"]["inbound"]),
                    ("出站消息", d["messages"]["outbound"]),
                ],
            },
            {
                "title": "聊天流",
                "rows": [
                    ("活跃流数", d["streams"]["active_count"]),
                ],
            },
            {
                "title": "插件",
                "rows": [
                    ("已加载", d["plugins"]["loaded_count"]),
                    ("加载失败", d["plugins"]["failed_count"]),
                    ("已加载列表", d["plugins"]["loaded_names"]),
                ],
            },
            {
                "title": "组件分布",
                "rows": [
                    *[
                        (f"  {ct}", cnt)
                        for ct, cnt in d["components"]["by_type"].items()
                    ],
                ],
            },
        ]
        return await self._render_and_send("Bot 业务数据", sections)

    @cmd_route("业务")
    async def handle_business_cn(self, hours: float = 0.0) -> tuple[bool, str]:
        return await self.handle_business(hours=hours)

    # ------------------------------------------------------------------
    # LLM 指标
    # ------------------------------------------------------------------

    @cmd_route("llm")
    async def handle_llm(self, hours: float = 0.0) -> tuple[bool, str]:
        h = self._resolve_hours(hours if hours > 0 else None, "llm")
        mgr = get_status_manager()
        d = await mgr.get_llm_status(hours=h)

        sections = [
            {
                "title": f"LLM 运营指标 · 窗口 {d['window_hours']:.1f}h",
                "rows": [
                    ("总请求数", d["total_requests"]),
                    ("成功 / 失败", f"{d['success_count']} / {d['error_count']}"),
                    ("成功率", d["success_rate"]),
                    ("Prompt Token", d["total_prompt_tokens"]),
                    ("Completion Token", d["total_completion_tokens"]),
                    ("总 Token", d["total_tokens"]),
                    ("缓存命中率", d["cache_hit_rate"]),
                    ("总成本", f"${d['total_cost']:.6f}"),
                    ("平均延迟", f"{d['avg_latency_ms']:.1f} ms"),
                ],
            },
        ]
        return await self._render_and_send("Bot LLM 运营指标", sections)

    # ------------------------------------------------------------------
    # 全部
    # ------------------------------------------------------------------

    @cmd_route("all")
    async def handle_all(self, hours: float = 0.0) -> tuple[bool, str]:
        h_arg = hours if hours > 0 else None
        biz_h = self._resolve_hours(h_arg, "all")
        llm_h = self._resolve_hours(h_arg, "all")

        mgr = get_status_manager()
        d = await mgr.get_all_status(business_hours=biz_h, llm_hours=llm_h)
        rt = d["runtime"]
        biz = d["business"]
        llm = d["llm"]

        biz_period = biz["messages"].get("period_label", f"{biz_h:.0f}h" if biz_h else "今日")

        sections = [
            {
                "title": "适配器",
                "rows": [
                    ("在线适配器", rt["adapter"]["active_count"]),
                    ("适配器签名", rt["adapter"]["active_signatures"]),
                ],
            },
            {
                "title": "调度器",
                "rows": [
                    ("调度器状态", rt["scheduler"]["is_running"]),
                    ("运行时长 (秒)", int(rt["scheduler"]["uptime_seconds"])),
                    ("调度任务总数", rt["scheduler"]["total_tasks"]),
                    ("正在运行", rt["scheduler"]["running_tasks"]),
                    ("调度成功率", rt["scheduler"]["success_rate"] * 100),
                ],
            },
            {
                "title": f"消息统计 · {biz_period}",
                "rows": [
                    ("总计 / 入站 / 出站",
                     f"{biz['messages']['total']}  /  {biz['messages']['inbound']}  /  {biz['messages']['outbound']}"),
                ],
            },
            {
                "title": "插件 & 流",
                "rows": [
                    ("已加载插件", biz["plugins"]["loaded_count"]),
                    ("加载失败", biz["plugins"]["failed_count"]),
                    ("活跃流 / 组件", f"{biz['streams']['active_count']} / {biz['components']['total_count']}"),
                ],
            },
            {
                "title": f"LLM · 窗口 {llm['window_hours']:.1f}h",
                "rows": [
                    ("请求数 (成功/失败)",
                     f"{llm['total_requests']} ({llm['success_count']}/{llm['error_count']})"),
                    ("成功率", llm["success_rate"]),
                    ("总 Token", llm["total_tokens"]),
                    ("缓存命中率", llm["cache_hit_rate"]),
                    ("总成本", f"${llm['total_cost']:.6f}"),
                    ("平均延迟", f"{llm['avg_latency_ms']:.1f} ms"),
                ],
            },
        ]
        return await self._render_and_send("Bot 全部状态", sections)

    @cmd_route("全部")
    async def handle_all_cn(self, hours: float = 0.0) -> tuple[bool, str]:
        return await self.handle_all(hours=hours)

    # ------------------------------------------------------------------
    # 帮助菜单
    # ------------------------------------------------------------------

    @cmd_route("help")
    async def handle_help(self) -> tuple[bool, str]:
        help_text = (
            "⚙️ Bot 状态查询插件帮助菜单\n\n"
            "主命令: /status 或 /状态\n\n"
            "子命令说明:\n"
            "1. /status [h] - 默认展示全部状态，可选指定时间窗口（小时，例如 /status 24）\n"
            "2. /status runtime | 运行 - 展示实时组件与系统状态（不受时间窗口限制）\n"
            "3. /status business | 业务 [h] - 展示业务与消息指标，可选指定时间窗口\n"
            "4. /status llm [h] - 展示 LLM 运营与成本指标，可选指定时间窗口\n"
            "5. /status all | 全部 [h] - 展示全部指标合集，可选指定时间窗口\n"
            "6. /status help | 帮助 - 查看本帮助菜单\n\n"
            "提示: 默认时间窗口可在配置文件中配置。"
        )
        return True, help_text

    @cmd_route("帮助")
    async def handle_help_cn(self) -> tuple[bool, str]:
        return await self.handle_help()