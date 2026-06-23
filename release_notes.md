## 更新内容

### 新功能
- 新增 `text_color`、`label_color`、`metric_color`、`title_color` 四种字体颜色自定义配置
  - `text_color`: 卡片标题颜色
  - `label_color`: 标签文字颜色
  - `metric_color`: 所有数据行值颜色（数值、字符串、列表等）
  - `title_color`: header 主标题颜色
- 所有数据行值统一使用 metric_color，一色控全局

### 修复
- 修复出站消息数始终显示 0 的 bug（person_id 查询条件从 isnull 改为 "bot"）
- Chromium 多级缓存检测，避免每次重启都重新下载
- Chromium 安装到插件 data/playwright 目录，Docker 容器重启后自动复用

### 改进
- 移除 is_count_key 关键词判断，所有 int 值统一使用 num CSS 类
- `.row-value` 和 `.row-value.str` 兜底颜色使用 metric_color

🎉 由 Claude Code 构建