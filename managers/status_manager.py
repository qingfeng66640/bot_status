"""Bot 状态数据聚合管理器。

负责聚合运行时状态、业务数据和 LLM 指标，为 StatusCommand 提供统一数据源。
复用 WebUI DashboardManager 的数据获取模式，直接调用框架内部 API。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from src.core.components.registry import get_global_registry
from src.core.components.types import ComponentType
from src.core.managers.adapter_manager import get_adapter_manager
from src.core.managers.event_manager import get_event_manager
from src.core.managers.plugin_manager import get_plugin_manager
from src.core.managers.stream_manager import get_stream_manager
from src.core.models.sql_alchemy import Messages
from src.kernel.concurrency import get_task_manager
from src.kernel.db.api.query import QueryBuilder
from src.kernel.llm.stats import get_llm_stats_collector
from src.kernel.scheduler import get_unified_scheduler


class StatusManager:
    """Bot 状态数据聚合管理器。"""

    def get_runtime_status(self) -> dict[str, Any]:
        """获取运行时状态数据（实时快照，不受时间窗口影响）。"""
        event_stats = get_event_manager().get_event_stats()
        task_stats = get_task_manager().get_stats()
        scheduler_stats = get_unified_scheduler().get_statistics()

        adapter_manager = get_adapter_manager()
        active_adapters = getattr(adapter_manager, "_active_adapters", {})

        return {
            "event": {
                "handler_count": event_stats.get("handler_count", 0),
                "temporary_handler_count": event_stats.get("temporary_handler_count", 0),
                "event_type_count": event_stats.get("event_type_count", 0),
                "total_subscriptions": event_stats.get("total_subscriptions", 0),
            },
            "task": {
                "total_tasks": task_stats.get("total_tasks", 0),
                "active_tasks": task_stats.get("active_tasks", 0),
                "daemon_tasks": task_stats.get("daemon_tasks", 0),
                "grouped_tasks": task_stats.get("grouped_tasks", 0),
                "groups": task_stats.get("groups", 0),
            },
            "scheduler": {
                "is_running": scheduler_stats.get("is_running", False),
                "uptime_seconds": scheduler_stats.get("uptime_seconds", 0.0),
                "total_tasks": scheduler_stats.get("total_tasks", 0),
                "running_tasks": scheduler_stats.get("running_tasks", 0),
                "success_rate": scheduler_stats.get("success_rate", 0.0),
            },
            "adapter": {
                "active_count": len(active_adapters),
                "active_signatures": list(active_adapters.keys()),
            },
        }

    async def get_business_status(self, *, hours: float | None = None) -> dict[str, Any]:
        """获取业务核心状态数据。

        Args:
            hours: 统计时间窗口（小时）。None 则统计当日（从今天 00:00 开始）。
        """
        if hours is not None and hours > 0:
            start_ts = time.time() - hours * 3600
        else:
            start_ts = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp()

        total = await QueryBuilder(Messages).filter(time__gte=start_ts).count()
        inbound = await QueryBuilder(Messages).filter(
            time__gte=start_ts, person_id__ne="bot"
        ).count()
        outbound = await QueryBuilder(Messages).filter(
            time__gte=start_ts, person_id="bot"
        ).count()

        stream_manager = get_stream_manager()
        active_streams = len(getattr(stream_manager, "_streams", {}))

        plugin_manager = get_plugin_manager()
        loaded_plugins = getattr(plugin_manager, "_loaded_plugins", {})
        failed_plugins = getattr(plugin_manager, "_failed_plugins", {})

        registry = get_global_registry()
        components_by_type = {}
        for component_type in ComponentType:
            components_by_type[component_type.value] = len(registry.get_by_type(component_type))

        period_label = f"{hours:.0f}h" if hours else "今日"

        return {
            "messages": {
                "total": int(total),
                "inbound": int(inbound),
                "outbound": int(outbound),
                "period_label": period_label,
            },
            "streams": {
                "active_count": active_streams,
            },
            "plugins": {
                "loaded_count": len(loaded_plugins),
                "loaded_names": list(loaded_plugins.keys()),
                "failed_count": len(failed_plugins),
            },
            "components": {
                "total_count": len(registry),
                "by_type": components_by_type,
            },
        }

    async def get_llm_status(self, *, hours: float | None = None) -> dict[str, Any]:
        """获取 LLM 运营指标。

        Args:
            hours: 统计时间窗口（小时）。None 则使用 LLM 统计收集器默认窗口。
        """
        if hours is not None and hours > 0:
            end_ts = time.time()
            start_ts = end_ts - hours * 3600
            summary = await get_llm_stats_collector().get_by_time_range(start_ts, end_ts)
            window_hours = hours
            # get_by_time_range 不返回 success_count/avg_latency，需要用 list_requests 补充
            requests = await get_llm_stats_collector().list_requests_by_time_range(
                start_ts, end_ts, limit=100000, offset=0
            )
            success_count = sum(1 for r in requests if r.get("success"))
            error_count = len(requests) - success_count
            success_rate = (success_count / len(requests) * 100) if requests else 0.0
            total_latency = sum(float(r.get("latency", 0)) for r in requests)
            avg_latency = (total_latency / len(requests)) if requests else 0.0
        else:
            summary = await get_llm_stats_collector().get_summary()
            window_hours = summary.get("window_hours", 5.0)
            success_count = summary.get("success_count", 0)
            error_count = summary.get("error_count", 0)
            success_rate = round(summary.get("success_rate", 0.0) * 100, 2)
            avg_latency = summary.get("avg_latency", 0.0)

        cache_total = summary.get("total_cache_hit_tokens", 0) + summary.get("total_cache_miss_tokens", 0)
        cache_hit_rate = (summary["total_cache_hit_tokens"] / cache_total * 100) if cache_total > 0 else 0.0

        return {
            "window_hours": float(window_hours),
            "total_requests": summary.get("total_requests", 0),
            "success_count": success_count,
            "error_count": error_count,
            "success_rate": success_rate,
            "total_prompt_tokens": summary.get("total_prompt_tokens", 0),
            "total_completion_tokens": summary.get("total_completion_tokens", 0),
            "total_tokens": summary.get("total_tokens", 0),
            "cache_hit_rate": round(cache_hit_rate, 2),
            "total_cost": summary.get("total_cost", 0.0),
            "avg_latency_ms": round(float(avg_latency) * 1000, 2),
        }

    async def get_all_status(self, *, business_hours: float | None = None,
                             llm_hours: float | None = None) -> dict[str, Any]:
        """获取全部状态数据。

        Args:
            business_hours: 业务数据时间窗口（小时），None=当日。
            llm_hours: LLM 数据时间窗口（小时），None=默认窗口。
        """
        runtime = self.get_runtime_status()
        business = await self.get_business_status(hours=business_hours)
        llm = await self.get_llm_status(hours=llm_hours)

        return {
            "runtime": runtime,
            "business": business,
            "llm": llm,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    # ------------------------------------------------------------------
    # 趋势图数据 (Hourly Binning)
    # ------------------------------------------------------------------

    async def get_hourly_trends(self, hours: int = 24) -> dict[str, Any]:
        """获取最近 N 小时的小时级趋势数据。

        Args:
            hours: 回溯小时数。
        """
        now = time.time()
        start_ts = now - hours * 3600

        # 1. 准备时间轴 (Labels)
        labels = []
        for i in range(hours + 1):
            ts = start_ts + i * 3600
            labels.append(datetime.fromtimestamp(ts).strftime("%H:00"))

        # 2. 获取消息趋势 (Python Binning)
        msgs = await QueryBuilder(Messages).filter(time__gte=start_ts).all()
        msg_inbound = [0] * (hours + 1)
        msg_outbound = [0] * (hours + 1)

        for m in msgs:
            # 计算偏移小时数
            offset = int((m.time - start_ts) // 3600)
            if 0 <= offset <= hours:
                if m.person_id == "bot":
                    msg_outbound[offset] += 1
                else:
                    msg_inbound[offset] += 1

        # 3. 获取 LLM 趋势 (SQL Aggregation)
        llm_collector = get_llm_stats_collector()
        llm_stats = await llm_collector.get_hourly_stats(hours=hours)
        llm_requests = [0] * (hours + 1)
        llm_tokens = [0] * (hours + 1)

        # llm_stats 返回的是有数据的点，需要映射到我们的 labels 偏移量上
        for s in llm_stats:
            # 找到最匹配的时间点
            s_ts = s["timestamp"]
            offset = int((s_ts - start_ts) // 3600)
            if 0 <= offset <= hours:
                llm_requests[offset] = s["total_requests"]
                llm_tokens[offset] = s["total_tokens"]

        return {
            "hours": hours,
            "labels": labels,
            "messages": {
                "inbound": msg_inbound,
                "outbound": msg_outbound,
            },
            "llm": {
                "requests": llm_requests,
                "tokens": llm_tokens,
            }
        }


_status_manager: StatusManager | None = None


def get_status_manager() -> StatusManager:
    """获取全局 StatusManager 单例。"""
    global _status_manager
    if _status_manager is None:
        _status_manager = StatusManager()
    return _status_manager