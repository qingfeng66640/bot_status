# Bot Status 状态查询插件

通过 `/status` 命令查询并展示 Bot 运行时状态、业务数据和 LLM 指标，以高清图片形式输出。

## 配置参数说明

插件支持对底座、边框、状态填充、进度条等各部分颜色以及圆角大小进行全面自定义。支持通过 `custom_html_path` 引用外部 HTML 模板，实现完全的排版与视觉定制。支持通过自定义 CSS/JS/静态资源文件在已有模板基础上叠加个性化前端。

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
| `text_color` | `str` | `"#e2e8f0"` | 卡片标题文字颜色，用于各卡片模块标题如 "// 适配器" (如 `"#e2e8f0"`)。 |
| `label_color` | `str` | `"#718096"` | 标签文字颜色，用于数据行左侧的字段名及 SYS_TIME 区域 (如 `"#718096"`)。 |
| `metric_color` | `str` | `"#ff9100"` | 数据行值的颜色，用于所有数据行右侧的值（数值、字符串、列表、百分比数字等）(如 `"#ff9100"`)。 |
| `title_color` | `str` | `"#e2e8f0"` | 标题文字颜色，用于 header-title 主标题 (如 `"#e2e8f0"`)。 |
| `chart_line_1` | `str` | `"#ff9100"` | 图表曲线颜色1（消息入站 / LLM 请求数），与 accent_color 配合使用。 |
| `chart_line_2` | `str` | `"#00ff66"` | 图表曲线颜色2（消息出站 / LLM Token），与 success_color 配合使用。 |
| `chart_axis_x_color` | `str` | `"#718096"` | 图表 X 轴刻度文字颜色，默认为 label_color 同色。 |
| `chart_axis_y_color` | `str` | `"#718096"` | 图表左 Y 轴刻度文字颜色，默认为 label_color 同色。 |
| `chart_axis_y_right_color` | `str` | `"#718096"` | 图表右 Y 轴（双轴模式的第二条曲线）刻度文字颜色，默认为 label_color 同色。 |

#### 自定义 HTML 模板

| 配置项键名 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| `custom_html_path` | `str` | `""` | **自定义 HTML 模板文件的绝对路径**。例如 `"C:/mofox/my_status.html"`。若留空或不配置，将默认加载插件内置的工业控制台模板。 |
| `chromium_cache_path` | `str` | `""` | **预下载的 Playwright Chromium 浏览器缓存目录的绝对路径**。例如 `"/data/ms-playwright"`。若配置且目录下已有可用浏览器，直接使用跳过在线下载。**离线部署方法**：先在能上网的机器执行 `playwright install chromium`，然后将 `~/.cache/ms-playwright/` 目录打包拷贝到容器内，通过 docker volume 挂载并配置此路径。 |

#### 自定义前端资源（CSS / JS / 静态资源）

通过 `custom_frontend_enabled` 开关统一控制，可在不替换完整 HTML 模板的情况下叠加自定义样式和脚本。所有静态资源会自动转为 `data:` URI 内联到渲染的 HTML 中（兼容 Playwright `page.set_content()` 的 opaque origin 限制）。

| 配置项键名 | 类型 | 默认值 | 描述 |
| :--- | :--- | :--- | :--- |
| `custom_frontend_enabled` | `bool` | `false` | **自定义前端资源注入总开关**。设为 `true` 后，下方的 CSS / JS / 静态资源路径才会加载并注入到渲染 HTML 中。 |
| `custom_css_path` | `str` | `""` | **自定义 CSS 文件绝对路径**。文件内容会被内联为 `<style>` 标签，追加在默认样式之后。例如 `"C:/my_styles/overrides.css"`。 |
| `custom_js_path` | `str` | `""` | **自定义 JavaScript 文件绝对路径**。文件内容会被内联为 `<script>` 标签，追加在所有脚本之后。可用于注入额外的图表逻辑或交互行为。例如 `"C:/my_styles/extra.js"`。 |
| `static_resources_dir` | `str` | `""` | **静态资源目录绝对路径**。目录下所有文件（图片、字体等）会转为 `data:` URI 并通过模板变量 `static_resources` 提供给模板引用。仅扫描目录顶层文件，不递归子目录。例如 `"C:/my_styles/assets/"`。 |

**使用示例**：

```toml
[style]
custom_frontend_enabled = true
custom_css_path = "C:/my_styles/overrides.css"
custom_js_path = "C:/my_styles/extra.js"
static_resources_dir = "C:/my_styles/assets/"
```

在自定义 HTML 模板中引用静态资源：

```html
<img src="{{ static_resources['logo.png'] }}" />
<style>
  @font-face {
    font-family: 'CustomFont';
    src: url('{{ static_resources['my-font.woff2'] }}');
  }
</style>
```

**注意**：
- 开关关闭时，即使填写了文件路径也不会加载，渲染行为保持不变
- 文件/目录不存在时会输出 warning 日志，不影响正常渲染
- 与 `custom_html_path` 互不干扰：可以只叠加 CSS 不改模板，也可以同时使用两者

---

### 自定义 HTML 模板开发指南

如果您指定了 `custom_html_path`，渲染器将读取并渲染您的自定义 Jinja2 模板。编写自定义模板时，可用的变量结构如下：

#### 1. 基础变量

| 变量 | 类型 | 说明 |
| :--- | :--- | :--- |
| `title` | `str` | 状态图片的标题 (例如 `"Bot 运行时状态"`)。 |
| `timestamp` | `str` | 图片生成的时间戳，格式为 `"YYYY-MM-DD HH:MM:SS"`。 |
| `has_chart` | `bool` | 当前页面是否包含图表 Section（可用于控制布局，例如图表时卡片全宽）。 |
| `chart_js` | `str` | Chart.js 库的完整源码，需用 `{{ chart_js \| safe }}` 注入为 `<script>` 标签。 |
| `style` | `dict` | 包含 `[style]` 样式色盘所有属性的字典。推荐在 CSS 中作为 CSS 变量注入。 |
| `custom_css` | `str` | 自定义 CSS 内容（开关关闭时为空字符串），需用 `{% if custom_css %}<style>{{ custom_css \| safe }}</style>{% endif %}` 注入。 |
| `custom_js` | `str` | 自定义 JavaScript 内容（开关关闭时为空字符串），需用 `{% if custom_js %}<script>{{ custom_js \| safe }}</script>{% endif %}` 注入。 |
| `static_resources` | `dict[str,str]` | 文件名 → `data:` URI 的映射字典，开关关闭时为空字典。 |

CSS 变量注入示例：

```css
:root {
  --bg-color: {{ style.bg_color | default('#0d0f12') }};
  --border-color: {{ style.border_color | default('#2d3748') }};
  --accent-color: {{ style.accent_color | default('#ff9100') }};
  --success-color: {{ style.success_color | default('#00ff66') }};
  --warning-color: {{ style.warning_color | default('#ff9100') }};
  --danger-color: {{ style.danger_color | default('#ff1744') }};
  --border-radius: {{ style.border_radius | default('4px') }};
  --text-color: {{ style.text_color | default('#e2e8f0') }};
  --label-color: {{ style.label_color | default('#718096') }};
  --metric-color: {{ style.metric_color | default('#ff9100') }};
  --title-color: {{ style.title_color | default('#e2e8f0') }};
  --chart-line-1: {{ style.chart_line_1 | default('#ff9100') }};
  --chart-line-2: {{ style.chart_line_2 | default('#00ff66') }};
  --chart-axis-x: {{ style.chart_axis_x | default('#718096') }};
  --chart-axis-y: {{ style.chart_axis_y | default('#718096') }};
  --chart-axis-y-right: {{ style.chart_axis_y_right | default('#718096') }};
}
```

#### 2. `sections` 数据结构

`sections` 列表包含两种类型的元素：**数据卡片** 和 **图表卡片**。

##### 数据卡片 (Data Section)

```jinja2
{% for s in sections %}
  {% if s.type != "chart" %}
    <!-- s.title: 卡片标题，如 "适配器"、"消息统计 · 24h" -->
    <!-- s.accent: 顶部色条颜色类名 (blue/green/orange/purple/cyan/red) -->
    <div class="card">
      <div class="card-accent {{ s.accent }}"></div>
      <h3>// {{ s.title }}</h3>

      {% for r in s.rows %}
        <!-- r.key:   指标名 (str) -->
        <!-- r.value: 格式化后的 HTML 值 (str)，必须用 safe 渲染 -->
        <!-- r.css:   CSS 辅助类 (str) — "num"/"cost"/"str" -->
        <div class="row">
          <span class="key">{{ r.key }}</span>
          <span class="value {{ r.css }}">{{ r.value | safe }}</span>
        </div>
      {% endfor %}
    </div>
  {% endif %}
{% endfor %}
```

##### 图表卡片 (Chart Section)

```jinja2
{% for s in sections %}
  {% if s.type == "chart" %}
    <!-- s.title:       图表标题 (str) -->
    <!-- s.chart_type:  图表类型 — "area" (消息出入站趋势) | "llm_trend" (LLM请求数/Token趋势) -->
    <!-- s.data.labels: X 轴标签列表 (list[str]) -->
    <!-- s.data.datasets: 数据集列表，每个含 label (str) 和 data (list[float]) -->
    <div class="card full-width">
      <div class="card-accent {{ s.accent }}"></div>
      <h3>// {{ s.title }} <span>[TREND]</span></h3>
      <canvas id="chart-{{ loop.index }}"></canvas>
    </div>
  {% endif %}
{% endfor %}
```

**图表双轴说明**：`area` 和 `llm_trend` 两种图表类型默认启用双 Y 轴模式。第 1 条数据集使用左 Y 轴（颜色由 `chart_axis_y_color` 控制），第 2 条及后续数据集使用右 Y 轴（颜色由 `chart_axis_y_right_color` 控制），避免出入站消息量级差异（或 LLM 请求数 vs Token 量级差异）导致某条曲线被压扁。

##### 行数据变量 `r` 说明
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