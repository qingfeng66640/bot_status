"""Bot 状态图片渲染工具。

使用 Jinja2 模板 + Playwright 无头浏览器将状态数据渲染为高清 PNG 图片。
模块导入时自动启动后台线程下载 Chromium，首次 /status 请求不需等待。
"""

from __future__ import annotations

import asyncio
import base64
import os
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import jinja2
from playwright.async_api import async_playwright

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

# 全局浏览器实例（懒启动，复用）
_pw: Any = None
_browser: Any = None
_lock = asyncio.Lock()

# 后台安装状态
_install_state = {"done": False, "error": None, "started": False}
_install_lock = threading.Lock()


class BrowserNotAvailableError(Exception):
    """Playwright Chromium 浏览器未就绪（仍在后台下载中或安装失败）。"""


def _install_chromium_background() -> None:
    """后台线程：通过国内镜像下载 Chromium 浏览器 + 系统依赖。"""
    global _install_state

    with _install_lock:
        if _install_state["started"]:
            return
        _install_state["started"] = True

    # 国内镜像加速 Playwright 浏览器下载
    env = {**os.environ, "PLAYWRIGHT_DOWNLOAD_HOST": "https://npmmirror.com/mirrors/playwright/"}

    # 1. 安装 Chromium 浏览器二进制
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True,
            timeout=600,
            check=True,
            env=env,
        )
    except subprocess.CalledProcessError as e:
        with _install_lock:
            _install_state["error"] = f"Chromium 下载失败: {e.stderr or e}"
        return

    # 2. 安装系统级依赖
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install-deps", "chromium"],
            capture_output=True,
            text=True,
            timeout=300,
            check=True,
        )
    except subprocess.CalledProcessError:
        pass

    with _install_lock:
        _install_state["done"] = True


def _get_install_status() -> dict:
    """获取当前 Chromium 安装状态（线程安全）。"""
    with _install_lock:
        return dict(_install_state)


# 模块导入时立即启动后台下载（非阻塞）
_bg_thread = threading.Thread(target=_install_chromium_background, daemon=True, name="pwt-install")
_bg_thread.start()


async def _get_browser():
    """获取全局复用的异步浏览器实例（线程安全）。

    如果 Chromium 仍在后台下载中，抛出 BrowserNotAvailableError 并提示稍后重试。
    """
    global _pw, _browser

    status = _get_install_status()
    if status["error"]:
        raise BrowserNotAvailableError(f"Chromium 安装失败: {status['error']}")
    if not status["done"]:
        raise BrowserNotAvailableError("Chromium 浏览器正在后台下载中，请稍后重试。首次下载约需 2-5 分钟。")

    if _browser is None:
        async with _lock:
            if _browser is None:
                try:
                    _pw = await async_playwright().start()
                    _browser = await _pw.chromium.launch(
                        headless=True,
                        args=["--disable-gpu", "--no-sandbox", "--disable-setuid-sandbox"],
                    )
                except Exception as e:
                    msg = str(e)
                    if "Executable doesn't exist" in msg:
                        raise BrowserNotAvailableError(
                            "Playwright Chromium 浏览器未安装，请在部署环境中执行：\n"
                            "  playwright install chromium\n"
                            "  playwright install-deps chromium"
                        ) from e
                    raise BrowserNotAvailableError(
                        f"Playwright 浏览器启动失败: {msg}"
                    ) from e
    return _browser


def _accent_class(title: str) -> str:
    """根据标题关键词返回顶部色条 CSS 类名。"""
    m = {
        "适配器": "blue", "adapter": "blue",
        "调度器": "orange", "scheduler": "orange",
        "任务": "green", "task": "green",
        "事件": "purple", "event": "purple",
        "消息": "blue", "message": "blue",
        "流": "cyan", "stream": "cyan",
        "插件": "purple", "plugin": "purple",
        "组件": "blue", "component": "blue",
        "LLM": "orange", "llm": "orange",
    }
    t = title.lower()
    for kw, cls in m.items():
        if kw in t:
            return cls
    return "blue"


class ImageRenderer:
    """Bot 状态图片渲染器 — HTML + 浏览器截图方案。

    使用 Jinja2 模板渲染 HTML，通过 Playwright 截图转为 PNG。
    浏览器实例在首次使用时启动并全局复用。
    """

    WIDTH = 720
    DEVICE_SCALE = 2  # Retina 2x 高清

    def __init__(self) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(_TEMPLATE_DIR)),
            autoescape=True,
        )

    async def render_to_base64(
        self,
        title: str,
        sections: list[dict[str, Any]],
        style: dict[str, str] | None = None,
        custom_template_path: str = "",
    ) -> str:
        """渲染状态数据为 base64 PNG。

        sections 格式: [{"title": str, "rows": [(key, value), ...]}]
        value 可以是 str / int / float / bool / list。
        style 支持传入自定义颜色和圆角配置字典。
        custom_template_path 支持指定外部 HTML 模板文件的绝对路径。
        """
        processed = self._process_sections(sections)

        if custom_template_path:
            p = Path(custom_template_path)
            if p.is_file():
                custom_env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader(str(p.parent)),
                    autoescape=True,
                )
                tmpl = custom_env.get_template(p.name)
            else:
                raise FileNotFoundError(f"未找到指定的自定义 HTML 模板文件: {custom_template_path}")
        else:
            tmpl = self._env.get_template("status.html")

        html = tmpl.render(
            title=title,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            sections=processed,
            style=style or {},
        )

        browser = await _get_browser()
        page = await browser.new_page(
            viewport={"width": self.WIDTH, "height": 500},
            device_scale_factor=self.DEVICE_SCALE,
        )
        await page.set_content(html, wait_until="networkidle")

        content_height = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size(
            {"width": self.WIDTH, "height": max(content_height, 100)}
        )
        await page.set_content(html, wait_until="networkidle")

        screenshot = await page.screenshot(full_page=True)
        await page.close()

        return base64.b64encode(screenshot).decode("utf-8")

    def _process_sections(
        self, sections: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """将原始 sections 转为模板所需的格式，处理值和样式。"""
        result = []
        for sec in sections:
            rows = []
            for key, value in sec.get("rows", []):
                display, css = self._format_value(key, value)
                rows.append({"key": key, "value": display, "css": css})
            result.append({
                "title": sec["title"],
                "accent": sec.get("accent") or _accent_class(sec["title"]),
                "rows": rows,
            })
        return result

    def _format_value(self, key: str, value: Any) -> tuple[str, str]:
        """将原始 value 转为 HTML 安全字符串 + CSS 类名。"""
        kl = key.lower()
        is_pct_key = any(
            kw in kl for kw in ("成功率", "命中率", "rate", "success")
        )
        is_count_key = any(
            kw in kl
            for kw in ("total", "active", "请求", "消息", "token", "tokens", "总数", "count")
        )

        # bool → 圆点
        if isinstance(value, bool):
            dot = (
                '<span class="status-dot ok"></span>'
                if value
                else '<span class="status-dot err"></span>'
            )
            label = "运行中" if value else "已停止"
            return f"{dot}{label}", "str"

        # 百分比 float/int → 进度条
        if isinstance(value, (int, float)) and is_pct_key:
            pct = float(value)
            bar_cls = "high" if pct >= 90 else ("mid" if pct >= 70 else "low")
            return (
                f'<span class="bar-wrap">'
                f'<span class="bar-track">'
                f'<span class="bar-fill {bar_cls}" style="width: {min(pct, 100):.0f}px;"></span>'
                f'</span>'
                f'<span class="row-value num">{pct:.1f}%</span>'
                f'</span>'
            ), "num"

        # int → 千分位格式化
        if isinstance(value, int):
            formatted = f"{value:,}" if value >= 1000 else str(value)
            css = "num" if is_count_key else "str"
            return formatted, css

        # float → 两位小数
        if isinstance(value, float):
            return f"{value:.2f}", "num"

        # list → 简短预览
        if isinstance(value, list):
            if not value:
                return "—", "str"
            preview = ", ".join(str(v) for v in value[:2])
            tail = f" …+{len(value) - 2}" if len(value) > 2 else ""
            return f"{preview}{tail}", "str"

        # dict → k:v 拼接
        if isinstance(value, dict):
            parts = [f"{k}: {v}" for k, v in value.items()]
            return ", ".join(parts) if parts else "—", "str"

        if value is None or value == "":
            return "—", "str"

        s = str(value)
        if "运行中" in s:
            return f'<span class="status-dot ok"></span>{s}', "str"
        if "已停止" in s:
            return f'<span class="status-dot err"></span>{s}', "str"
        if "$" in s:
            return s, "cost"

        return s, "str"