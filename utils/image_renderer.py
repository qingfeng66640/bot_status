"""Bot 状态图片渲染工具。

使用 Jinja2 模板 + Playwright 无头浏览器将状态数据渲染为高清 PNG 图片。
模块导入后首次 /status 请求会自动触发异步后台下载 Chromium，不阻塞事件循环。
下载镜像按优先级依次尝试：npmmirror → 腾讯云 → 华为云 → Yandex → 官方。
"""

from __future__ import annotations

import asyncio
import base64
import mimetypes
import os
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

import jinja2
from playwright.async_api import async_playwright

from src.app.plugin_system.api.log_api import get_logger

_log = get_logger("bot_status.image")

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

# 插件自身 data 目录下的 Chromium 缓存路径
_PLUGIN_PLAYWRIGHT_DIR = Path(__file__).resolve().parent.parent / "data" / "playwright"

# 模块加载时预读取 Chart.js，避免每次渲染都读盘
_CHART_JS_CACHE: str | None = None


def _load_chart_js() -> str:
    """加载本地打包的 Chart.js，若无则返回空字符串。"""
    global _CHART_JS_CACHE
    if _CHART_JS_CACHE is not None:
        return _CHART_JS_CACHE
    chart_js_path = _STATIC_DIR / "chart.umd.min.js"
    if chart_js_path.is_file():
        _log.info("使用本地打包的 Chart.js")
        _CHART_JS_CACHE = chart_js_path.read_text(encoding="utf-8")
    else:
        _log.warning("本地 Chart.js 未找到，图表将无法渲染")
        _CHART_JS_CACHE = ""
    return _CHART_JS_CACHE


def _build_data_uri(file_path: Path) -> str:
    """读取文件并返回 data: URI 字符串。

    根据文件扩展名自动推断 MIME 类型，内容统一 base64 编码。
    """
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type is None:
        mime_type = "application/octet-stream"
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _load_custom_frontend_resources(
    custom_css_path: str,
    custom_js_path: str,
    static_resources_dir: str,
) -> dict[str, Any]:
    """加载自定义前端资源，返回模板可用的字典。

    Returns:
        dict with keys:
          - custom_css: CSS 文本或空字符串
          - custom_js: JS 文本或空字符串
          - static_resources: 文件名 -> data: URI 映射
    """
    result: dict[str, Any] = {
        "custom_css": "",
        "custom_js": "",
        "static_resources": {},
    }

    if custom_css_path:
        css_file = Path(custom_css_path)
        if css_file.is_file():
            result["custom_css"] = css_file.read_text(encoding="utf-8")
        else:
            _log.warning(f"自定义 CSS 文件不存在: {custom_css_path}")

    if custom_js_path:
        js_file = Path(custom_js_path)
        if js_file.is_file():
            result["custom_js"] = js_file.read_text(encoding="utf-8")
        else:
            _log.warning(f"自定义 JS 文件不存在: {custom_js_path}")

    if static_resources_dir:
        res_dir = Path(static_resources_dir)
        if res_dir.is_dir():
            for f in res_dir.iterdir():
                if f.is_file():
                    result["static_resources"][f.name] = _build_data_uri(f)
            _log.info(f"已加载 {len(result['static_resources'])} 个静态资源")
        else:
            _log.warning(f"静态资源目录不存在: {static_resources_dir}")

    return result


# 全局浏览器实例（懒启动，复用）
_pw: Any = None
_browser: Any = None
_lock = asyncio.Lock()

# 后台安装状态（纯 asyncio，无需线程锁）
_install_task: asyncio.Task | None = None
_install_done = False
_install_error: str | None = None

# 按优先级排列的镜像列表，最后一个为 None（使用官方源）
_MIRRORS = [
    "https://npmmirror.com/mirrors/playwright",
    "https://mirrors.cloud.tencent.com/playwright",
    "https://mirrors.huaweicloud.com/playwright",
    "https://http.mirror.yandex.ru/mirrors/playwright.azureedge.net",
    None,  # 兜底：官方源
]


class BrowserNotAvailableError(Exception):
    """Playwright Chromium 浏览器未就绪（仍在后台下载中或安装失败）。"""


def _find_chromium_executable(search_root: str | Path) -> str | None:
    """在指定目录中递归搜索 Chromium 可执行文件，返回找到的第一个路径。"""
    cache_dir = Path(search_root)
    if not cache_dir.is_dir():
        return None
    headless = sorted(cache_dir.glob("**/chrome-headless-shell-linux64/chrome-headless-shell"), reverse=True)
    chrome = sorted(cache_dir.glob("**/chrome-linux64/chrome"), reverse=True)
    win_headless = sorted(cache_dir.glob("**/chrome-headless-shell-win64/chrome-headless-shell.exe"), reverse=True)
    win_chrome = sorted(cache_dir.glob("**/chrome-win64/chrome.exe"), reverse=True)
    candidates = headless + chrome + win_headless + win_chrome
    if candidates:
        path = str(candidates[0])
        os.chmod(path, 0o755)
        return path
    return None


def _get_default_playwright_cache_dirs() -> list[Path]:
    """返回 Playwright 在各平台的默认浏览器缓存目录列表。"""
    home = Path.home()
    if sys.platform == "win32":
        return [home / "AppData" / "Local" / "ms-playwright"]
    elif sys.platform == "darwin":
        return [home / "Library" / "Caches" / "ms-playwright"]
    else:
        return [
            home / ".cache" / "ms-playwright",
            Path("/root/.cache/ms-playwright"),
        ]


def _check_mirror_available(url: str, timeout: float = 10) -> bool:
    """对镜像 URL 做快速 HEAD 探测，返回是否可达（非 404/403）。"""
    try:
        req = urllib.request.Request(url, method="HEAD")
        resp = urllib.request.urlopen(req, timeout=timeout)
        ok = resp.status < 400
        _log.info(f"[镜像探测] {url} → HTTP {resp.status} {'✓ 可用' if ok else '✗ 不可用'}")
        return ok
    except Exception as e:
        _log.warning(f"[镜像探测] {url} → 不可达 ({e})")
        return False


async def _try_install_with_mirror(mirror: str | None, target_dir: str = "") -> bool:
    """使用指定镜像安装 Chromium，返回是否成功。

    若 mirror 为 None 则不设 PLAYWRIGHT_DOWNLOAD_HOST，使用官方默认源。
    若 target_dir 指定，则设置 PLAYWRIGHT_BROWSERS_PATH 将浏览器安装到该目录。
    """
    env = dict(os.environ)
    label = mirror or "官方源"
    _log.info(f"[Chromium 安装] 正在尝试: {label}")
    if mirror:
        env["PLAYWRIGHT_DOWNLOAD_HOST"] = mirror
    if target_dir:
        env["PLAYWRIGHT_BROWSERS_PATH"] = target_dir
        _log.info(f"[Chromium 安装] 目标目录: {target_dir}")

    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "playwright", "install", "chromium",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        if proc.returncode != 0:
            err_text = stderr.decode() if stderr else f"exit code {proc.returncode}"
            _log.warning(f"[Chromium 安装] {label} 失败: {err_text.strip()}")
            return False
        _log.info(f"[Chromium 安装] {label} 安装成功")
        return True
    except asyncio.TimeoutError:
        _log.warning(f"[Chromium 安装] {label} 超时 (600s)")
        return False
    except Exception as e:
        _log.warning(f"[Chromium 安装] {label} 异常: {e}")
        return False


async def _install_system_deps(max_retries: int = 5, retry_delay: float = 10) -> bool:
    """安装 Chromium 系统级依赖（libglib-2.0.so.0 等）。

    apt 锁可能被 Docker 容器启动时的 apt-get update 等进程占用，
    先等待重试；若锁持续不释放，则主动杀掉持有进程并清理锁文件后重试。
    """
    for attempt in range(1, max_retries + 1):
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, "-m", "playwright", "install-deps", "chromium",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode == 0:
                _log.info(f"[系统依赖] 安装成功 (attempt {attempt})")
                return True
            err_text = (stderr.decode(errors="replace") if stderr else "") + (
                stdout.decode(errors="replace") if stdout else ""
            )
            if "Could not get lock" in err_text or "Unable to lock" in err_text:
                if attempt < max_retries:
                    _log.warning(
                        f"[系统依赖] apt 锁被占用，{retry_delay}s 后重试 "
                        f"({attempt}/{max_retries})"
                    )
                    await asyncio.sleep(retry_delay)
                    continue
                # 最后一次重试也遇到锁 → 主动清理后立即重试
                _log.warning(
                    f"[系统依赖] apt 锁持续被占用 ({max_retries} 次重试均失败)，"
                    "尝试强制清理锁..."
                )
                if await _force_clear_apt_lock():
                    _log.info("[系统依赖] 锁已清理，立即重试安装...")
                    # 直接在循环内再试一次（不走 continue，避免 range 耗尽）
                    try:
                        proc = await asyncio.create_subprocess_exec(
                            sys.executable, "-m", "playwright", "install-deps", "chromium",
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE,
                        )
                        stdout, stderr = await asyncio.wait_for(
                            proc.communicate(), timeout=300
                        )
                        if proc.returncode == 0:
                            _log.info("[系统依赖] 强制清理后安装成功")
                            return True
                        err2 = (
                            stderr.decode(errors="replace") if stderr else ""
                        )
                        _log.warning(
                            f"[系统依赖] 强制清理后安装仍失败: "
                            f"{err2.strip()[:300]}"
                        )
                    except Exception as e:
                        _log.warning(f"[系统依赖] 强制清理后安装异常: {e}")
            else:
                _log.warning(
                    f"[系统依赖] 安装返回非零 (attempt {attempt}/{max_retries}): "
                    f"{err_text.strip()[:300]}"
                )
        except asyncio.TimeoutError:
            _log.warning(f"[系统依赖] 安装超时 (attempt {attempt}/{max_retries})")
        except Exception as e:
            _log.warning(f"[系统依赖] 安装异常 (attempt {attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            await asyncio.sleep(retry_delay)
    return False


async def _force_clear_apt_lock() -> bool:
    """强制清理 apt 锁：杀掉持有锁的进程并删除锁文件。"""
    try:
        # 1. 查出持有 apt 锁的进程 PID 并杀掉
        proc = await asyncio.create_subprocess_exec(
            "fuser", "-k", "/var/lib/apt/lists/lock",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        _log.info("[系统依赖] 已杀掉持有 /var/lib/apt/lists/lock 的进程")
    except Exception:
        pass

    try:
        proc = await asyncio.create_subprocess_exec(
            "fuser", "-k", "/var/lib/dpkg/lock-frontend",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        _log.info("[系统依赖] 已杀掉持有 /var/lib/dpkg/lock-frontend 的进程")
    except Exception:
        pass

    # 2. 清理残留锁文件
    lock_files = [
        "/var/lib/apt/lists/lock",
        "/var/lib/dpkg/lock-frontend",
        "/var/lib/dpkg/lock",
        "/var/cache/apt/archives/lock",
    ]
    for lock_file in lock_files:
        try:
            os.remove(lock_file)
            _log.info(f"[系统依赖] 已删除锁文件: {lock_file}")
        except FileNotFoundError:
            pass
        except Exception as e:
            _log.warning(f"[系统依赖] 删除锁文件失败 ({lock_file}): {e}")

    # 3. 修复可能中断的 dpkg 状态
    try:
        proc = await asyncio.create_subprocess_exec(
            "dpkg", "--configure", "-a",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=60)
        _log.info("[系统依赖] dpkg --configure -a 完成")
    except Exception:
        pass

    return True


async def _install_chromium_async() -> None:
    """异步后台任务：将 Chromium 安装到插件自身 data/playwright 目录。

    按优先级依次尝试各镜像下载，下载期间不阻塞事件循环。
    安装目标为插件 data/playwright/ 目录，重启后自动复用。
    """
    global _install_done, _install_error

    _log.info("[Chromium 后台安装] 开始探测可用镜像...")

    # 确保目标目录存在
    _PLUGIN_PLAYWRIGHT_DIR.mkdir(parents=True, exist_ok=True)
    target_dir = str(_PLUGIN_PLAYWRIGHT_DIR.resolve())

    # 1. 按优先级遍历镜像安装 Chromium 浏览器二进制到插件 data 目录
    installed = False
    for mirror in _MIRRORS:
        label = mirror or "官方源"
        # 先快速探测镜像是否可访问（官方源跳过探测）
        if mirror is not None and not _check_mirror_available(mirror):
            _log.warning(f"[Chromium 后台安装] 跳过不可达镜像: {label}")
            continue

        if await _try_install_with_mirror(mirror, target_dir=target_dir):
            installed = True
            break

    if not installed:
        _install_error = "所有镜像均无法下载 Chromium（官方源也已尝试）"
        _log.error(f"[Chromium 后台安装] {_install_error}")
        return

    _log.info("[Chromium 后台安装] Chromium 安装完成，正在检查系统依赖...")

    # 2. 安装系统级依赖（带 apt 锁重试）
    deps_ok = await _install_system_deps()
    if deps_ok:
        _log.info("[Chromium 后台安装] 系统依赖安装完成")
    else:
        _log.warning("[Chromium 后台安装] 系统依赖安装失败，可能非 root 或 apt 锁持续占用")

    _install_done = True
    _log.info("[Chromium 后台安装] 全部就绪，浏览器可用")


async def _get_browser(cache_path: str = ""):
    """获取全局复用的异步浏览器实例（线程安全）。

    首次调用时自动触发后台异步下载 Chromium，不阻塞事件循环。
    如果 Chromium 仍在下载中，抛出 BrowserNotAvailableError 提示稍后重试。

    Args:
        cache_path: 可选的外部浏览器缓存路径。如果指定且目录下已有可用浏览器，直接使用跳过下载。
    """
    global _pw, _browser, _install_task, _install_done

    # 从缓存目录中查找 Chromium 可执行文件路径
    _executable_path: str | None = None

    # 1) 优先检查用户配置的外部缓存路径
    if cache_path and not _install_done and not _install_error:
        _log.info(f"[浏览器] 检测到外部缓存路径: {cache_path}")
        _executable_path = _find_chromium_executable(cache_path)
        if _executable_path:
            _log.info(f"[浏览器] 外部缓存命中: {_executable_path}")
        else:
            _log.warning(
                "[浏览器] 外部缓存目录中未找到 Chromium 可执行文件，"
                "将尝试插件 data 目录和默认缓存目录"
            )

    # 2) 检查插件自身 data/playwright 目录（上次在线安装的结果）
    if not _executable_path and not _install_done and not _install_error:
        _executable_path = _find_chromium_executable(_PLUGIN_PLAYWRIGHT_DIR)
        if _executable_path:
            _log.info(f"[浏览器] 插件 data 目录缓存命中: {_executable_path}")
        else:
            _log.debug(f"[浏览器] 插件 data 目录无缓存: {_PLUGIN_PLAYWRIGHT_DIR}")

    # 3) 未命中时检查 Playwright 默认缓存目录
    if not _executable_path and not _install_done and not _install_error:
        for cache_dir in _get_default_playwright_cache_dirs():
            _executable_path = _find_chromium_executable(cache_dir)
            if _executable_path:
                _log.info(f"[浏览器] 默认缓存命中: {_executable_path}")
                break

    # 4) 缓存命中后，标记安装完成（跳过在线下载）
    if _executable_path and not _install_done and not _install_error:
        _install_done = True
        _log.info("[浏览器] Chromium 已在缓存中就绪，跳过在线下载")

    # 5) 缓存未命中，触发后台在线安装（下载到插件 data/playwright）
    if not _install_done and _install_task is None:
        _log.info("[浏览器] 未找到缓存 Chromium，触发后台在线安装...")
        _install_task = asyncio.create_task(_install_chromium_async())

    if _install_error:
        raise BrowserNotAvailableError(f"Chromium 安装失败: {_install_error}")
    if not _install_done:
        raise BrowserNotAvailableError(
            "Chromium 浏览器正在后台异步下载中，请稍后重试。首次下载约需 2-5 分钟。"
        )

    _log.info("[浏览器] Chromium 已就绪，正在启动浏览器实例...")
    if _browser is None:
        async with _lock:
            if _browser is None:
                launch_kwargs: dict = {
                    "headless": True,
                    "args": ["--disable-gpu", "--no-sandbox", "--disable-setuid-sandbox"],
                }
                if _executable_path:
                    launch_kwargs["executable_path"] = _executable_path
                try:
                    _pw = await async_playwright().start()
                    _browser = await _pw.chromium.launch(**launch_kwargs)
                    _log.info("[浏览器] 浏览器实例启动成功")
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
        chromium_cache_path: str = "",
        custom_css_path: str = "",
        custom_js_path: str = "",
        static_resources_dir: str = "",
        custom_frontend_enabled: bool = False,
    ) -> str:
        """渲染状态数据为 base64 PNG。

        sections 格式: [{"title": str, "rows": [(key, value), ...]}]
        value 可以是 str / int / float / bool / list。
        style 支持传入自定义颜色和圆角配置字典。
        custom_template_path 支持指定外部 HTML 模板文件的绝对路径。
        chromium_cache_path 支持指定预下载的外部 Chromium 缓存目录，跳过在线下载。
        custom_css_path / custom_js_path / static_resources_dir 支持自定义前端资源注入。
        custom_frontend_enabled 控制是否启用自定义资源加载。
        """
        processed = self._process_sections(sections)
        has_chart = any(s.get("type") == "chart" for s in processed)

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

        # 加载自定义前端资源（开关控制）
        custom_resources: dict[str, Any] = {"custom_css": "", "custom_js": "", "static_resources": {}}
        if custom_frontend_enabled:
            custom_resources = _load_custom_frontend_resources(
                custom_css_path, custom_js_path, static_resources_dir
            )

        html = tmpl.render(
            title=title,
            timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            sections=processed,
            style=style or {},
            has_chart=has_chart,
            chart_js=_load_chart_js(),
            custom_css=custom_resources["custom_css"],
            custom_js=custom_resources["custom_js"],
            static_resources=custom_resources["static_resources"],
        )

        browser = await _get_browser(cache_path=chromium_cache_path)
        page = await browser.new_page(
            viewport={"width": self.WIDTH, "height": 500},
            device_scale_factor=self.DEVICE_SCALE,
        )
        await page.set_content(html, wait_until="domcontentloaded", timeout=30000)

        content_height = await page.evaluate("document.body.scrollHeight")
        await page.set_viewport_size(
            {"width": self.WIDTH, "height": max(content_height, 100)}
        )
        await page.set_content(html, wait_until="domcontentloaded", timeout=30000)

        # 等待图表绘制完成后再截图（无图表时 __chartsReady 始终为 true）
        if has_chart:
            try:
                await page.wait_for_function("window.__chartsReady === true", timeout=10000)
            except Exception:
                _log.warning("等待图表渲染超时，继续截图")

        screenshot = await page.screenshot(full_page=True)
        await page.close()

        return base64.b64encode(screenshot).decode("utf-8")

    def _process_sections(
        self, sections: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """将原始 sections 转为模板所需的格式，处理值和样式。"""
        result = []
        for sec in sections:
            if sec.get("type") == "chart":
                result.append({
                    "title": sec["title"],
                    "type": "chart",
                    "chart_type": sec.get("chart_type", "area"),
                    "data": sec["data"],
                    "accent": sec.get("accent") or _accent_class(sec["title"]),
                })
                continue

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
            return formatted, "num"

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