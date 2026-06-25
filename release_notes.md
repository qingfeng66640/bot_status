## 更新内容

### 新功能
- 新增 **数据趋势图表**：在 `/status` 图片中展示消息出入站趋势和 LLM 请求/Token 消耗趋势
  - 面积图样式，工业控制台风格，支持渐变填充
  - 双 Y 轴模式：出入站分别使用左右轴，LLM 请求数与 Token 量使用左右轴，避免量级差异压扁曲线
  - 配置：`[chart]` > `enabled`（开关）和 `hours`（展示时长，默认 24h）
  - 本地内联 Chart.js，无需 CDN 外部加载
- 新增 **自定义前端资源注入**：通过 `custom_frontend_enabled` 开关统一控制
  - `custom_css_path`：自定义 CSS 文件，内联为 `<style>` 标签
  - `custom_js_path`：自定义 JavaScript 文件，内联为 `<script>` 标签
  - `static_resources_dir`：静态资源目录，文件自动转 `data:` URI，模板中通过 `static_resources` 字典引用
- 新增 **图表颜色配置**：`chart_line_1`、`chart_line_2`、`chart_axis_x_color`、`chart_axis_y_color`、`chart_axis_y_right_color`
- 新增 `permission_level` 配置项，支持自定义命令最低权限级别（owner/operator/user/guest）

### 优化
- 渲染改为后台异步任务，避免事件系统 5s 超时杀进程
- UI 全面刷新：机械螺丝装饰、卡片顶部色条、虚线分隔符、工业级进度条
- Chart.js 本地打包，避免 CDN 网络依赖
- 图例和坐标轴颜色支持通过 CSS 变量配置
- `page.set_content` 从 `networkidle` 改为 `domcontentloaded`，内联资源无需等待网络

### 修复
- LLM 趋势数据改用 Python 分箱聚合，兼容更广泛的数据格式
- Chart.js 颜色解析支持 rgba/hex 混合格式

🎉 由 Claude Code 构建