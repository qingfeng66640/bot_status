# Bot Status 状态查询插件

通过 `/status` 命令查询并展示 Bot 运行时状态、业务数据和 LLM 指标，以高清图片形式输出。

## 配置参数说明

插件支持对底座、边框、状态填充、进度条等各部分颜色以及圆角大小进行全面自定义。支持通过 `custom_html_path` 引用外部 HTML 模板，实现完全的排版与视觉定制。

### 配置项结构

配置位于 `config/bot_status.toml` (Neo-MoFox 规范配置文件)。

#### `[style]` 样式色盘及自定义模板

| 配置项键名 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| `bg_color` | `str` | `"#0d0f12"` | 控制台底座背景颜色，例如 `"#0d0f12"` 或 `"rgb(13, 15, 18)"`。 |
| `border_color` | `str` | `"#2d3748"` | 机架及面板的边框色，例如 `"#2d3748"`。 |
| `accent_color` | `str` | `"#ff9100"` | 核心指示色、警示斜纹装饰条、以及普通卡片高亮标志的颜色。 |
| `success_color` | `str` | `"#00ff66"` | 高成功率 (>=90%) 进度条、在线状态、正常运行指示灯的填充色。 |
| `warning_color` | `str` | `"#ff9100"` | 中等成功率 (70% ~ 90%) 进度条、警告指示灯的填充色。 |
| `danger_color` | `str` | `"#ff1744"` | 低成功率 (<70%) 进度条、异常离线状态的填充色。 |
| `border_radius` | `str` | `"4px"` | 卡片和机架的圆角大小，例如 `"4px"`, `"0px"` 或 `"8px"`。 |
| `custom_html_path` | `str` | `""` | **自定义 HTML 模板文件的绝对路径**。例如 `"C:/mofox/my_status.html"`。若留空或不配置，将默认加载插件内置的工业控制台模板。 |
| `chromium_cache_path` | `str` | `""` | **预下载的 Playwright Chromium 浏览器缓存目录的绝对路径**。例如 `"/data/ms-playwright"`。若配置且目录下已有可用浏览器，直接使用跳过在线下载。**离线部署方法**：先在能上网的机器执行 `playwright install chromium`，然后将 `~/.cache/ms-playwright/` 目录打包拷贝到容器内，通过 docker volume 挂载并配置此路径。 |

---

### 自定义 HTML 模板开发指南

如果您指定了 `custom_html_path`，渲染器将读取并渲染您的自定义 Jinja2 模板。编写自定义模板时，可用的变量结构如下：

#### 1. 基础变量
- `title` (`str`): 状态图片的标题 (例如 `"Bot 运行时状态"`)。
- `timestamp` (`str`): 图片生成的时间戳，格式为 `"YYYY-MM-DD HH:MM:SS"`。
- `style` (`dict`): 包含上述 `[style]` 样式色盘的属性字典。在 CSS 中可以直接作为 CSS 变量注入：
  ```css
  :root {
    --bg-color: {{ style.bg_color | default('#0d0f12') }};
    --border-color: {{ style.border_color | default('#2d3748') }};
    --accent-color: {{ style.accent_color | default('#ff9100') }};
    --success-color: {{ style.success_color | default('#00ff66') }};
    --warning-color: {{ style.warning_color | default('#ff9100') }};
    --danger-color: {{ style.danger_color | default('#ff1744') }};
    --border-radius: {{ style.border_radius | default('4px') }};
  }
  ```

#### 2. `sections` 数据结构
`sections` 列表包含多个卡片（模块）的数据。遍历 `sections` 即可渲染各状态块：

```jinja2
{% for s in sections %}
  <!-- 模块标题 -->
  <h3>// {{ s.title }}</h3>
  <!-- 顶部色条标识颜色类名 (可能有: blue, green, orange, purple, cyan, red) -->
  <div class="accent-bar {{ s.accent }}"></div>

  <!-- 遍历行数据 -->
  {% for r in s.rows %}
    <div class="row">
      <!-- 属性名 -->
      <span class="key">{{ r.key }}</span>
      <!-- 属性值 (已转义，或已包装为 status-dot 运行指示灯/bar-wrap 进度条 HTML，必须使用 safe 渲染) -->
      <span class="value {{ r.css }}">{{ r.value | safe }}</span>
    </div>
  {% endfor %}
{% endfor %}
```

##### 行数据变量 `r` 说明：
- `r.key` (`str`): 指标中文名称。
- `r.css` (`str`): 该行值的 CSS 辅助标记类。
  - `"num"`: 统计数值，推荐渲染为高亮数字颜色。
  - `"cost"`: 成本数值，包含美金符号（如 `"$0.000100"`）。
  - `"str"`: 普通文本或复杂组件包装。
- `r.value` (`str`): 渲染好的 HTML 字符串（带有状态标记的富文本）。
  - **布尔值**：会转换为带小圆点指示灯的文本，如 `<span class="status-dot ok"></span>运行中`
  - **百分比**：自动包装为带防滑斜纹的高对比度进度条，如：
    ```html
    <span class="bar-wrap">
      <span class="bar-track">
        <span class="bar-fill high" style="width: 100px;"></span>
      </span>
      <span class="row-value num">100.0%</span>
    </span>
    ```
  - **普通数值/字符串**：进行了千分位或格式化处理的纯文本。
