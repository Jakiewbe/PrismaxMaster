# PrismaX 低保助手 - 简化版

## 📋 简介

这是一个简化版的 PrismaX 自动化脚本，**只包含签到和评论功能**，去除了所有复杂的机器人控制逻辑、Python通信、GUI界面等。

## ✨ 功能特性

- ✅ **自动签到**：在指定时间窗口内自动执行早八签到
- ✅ **自动评论**：在指定时间窗口内自动发送评论
- ✅ **纯JS实现**：无需Python端，完全在浏览器中运行
- ✅ **轻量级**：代码量约300行，易于理解和维护
- ✅ **可配置**：所有时间窗口和评论内容都可自定义

## 🚀 安装步骤

### 1. 安装 Tampermonkey

- Chrome/Edge: [Chrome Web Store](https://chrome.google.com/webstore/detail/tampermonkey/dhdgffkkebhmkfjojejmpbldmpobfkfo)
- Firefox: [Firefox Add-ons](https://addons.mozilla.org/firefox/addon/tampermonkey/)
- Safari: [Safari Extension](https://apps.apple.com/app/tampermonkey/id1482490089)

### 2. 安装脚本

1. 打开 Tampermonkey 管理面板
2. 点击"添加新脚本"
3. 复制 `simple_checkin_comment.js` 的全部内容
4. 粘贴到编辑器中
5. 保存（Ctrl+S）

### 3. 配置（可选）

如果需要修改配置，有两种方式：

**方式1：直接修改脚本中的 CONFIG 对象**
- 打开 Tampermonkey 管理面板
- 找到"PrismaX 低保助手"脚本
- 点击编辑
- 修改 `CONFIG` 对象中的配置项
- 保存

**方式2：使用外部配置文件**
- 修改 `simple_config.js` 中的配置
- 将文件上传到可访问的URL（如GitHub Gist）
- 在 `simple_checkin_comment.js` 中修改配置文件URL

## ⚙️ 配置说明

### 签到功能配置

```javascript
morningEnabled: true,              // 是否启用签到
morningWindowStart: "08:01",       // 签到开始时间
morningWindowEnd: "08:06",         // 签到结束时间
morningRandomInsideWindow: true,   // 是否在窗口内随机执行
morningIgnoreDone: false,          // 是否忽略已完成标记
```

### 评论功能配置

```javascript
commentTask: {
    enabled: true,                 // 是否启用评论
    windowStart: "00:00",          // 评论开始时间
    windowEnd: "00:05",            // 评论结束时间
    randomInsideWindow: true,       // 是否在窗口内随机执行
    commentCount: { min: 5, max: 5 },  // 评论数量
    commentDelay: { min: 5000, max: 8000 },  // 评论间隔（毫秒）
    comments: [                    // 评论内容列表
        "评论1",
        "评论2",
        // ...
    ]
}
```

## 📝 使用说明

### 签到功能

1. 脚本会在每天 **08:01-08:06** 之间自动执行签到
2. 如果启用随机模式，会在窗口内随机选择时间执行
3. 签到完成后会在 localStorage 中记录，当天不会重复执行

### 评论功能

1. 脚本会在每天 **00:00-00:05** 之间自动执行评论任务
2. 默认发送 5 条评论，每条间隔 5-8 秒
3. 评论内容从预设列表中随机选择
4. 评论完成后会在 localStorage 中记录，当天不会重复执行

### 查看日志

打开浏览器控制台（F12），可以看到详细的执行日志：

```
[低保助手] 简化版签到和评论脚本已加载
[签到] 执行早八签到...
[评论任务] === 开始执行评论任务 ===
[评论] ✅ 已发送: "PrismaX demonstrates..."
```

## 🔧 常见问题

### Q: 脚本没有执行？

A: 检查以下几点：
1. 确认 Tampermonkey 已启用
2. 确认脚本已安装并启用
3. 检查时间窗口是否正确
4. 查看浏览器控制台是否有错误信息

### Q: 如何修改签到时间？

A: 编辑脚本中的 `CONFIG.morningWindowStart` 和 `CONFIG.morningWindowEnd`，格式为 "HH:MM"（24小时制）

### Q: 如何修改评论内容？

A: 编辑脚本中的 `CONFIG.commentTask.comments` 数组，添加或修改评论内容

### Q: 如何重置已完成状态？

A: 打开浏览器控制台（F12），执行以下命令：

```javascript
// 重置签到状态
localStorage.removeItem('simple_morning_done');

// 重置评论状态
localStorage.removeItem('simple_comment_task_done');
```

### Q: 脚本会占用很多资源吗？

A: 不会。脚本每5秒检查一次，只在时间窗口内执行操作，平时几乎不占用资源。

## 📊 与原版的区别

| 功能 | 原版 | 简化版 |
|------|------|--------|
| 机器人控制 | ✅ | ❌ |
| Python通信 | ✅ | ❌ |
| GUI界面 | ✅ | ❌ |
| 状态同步 | ✅ | ❌ |
| 签到功能 | ✅ | ✅ |
| 评论功能 | ✅ | ✅ |
| 代码量 | ~2000行 | ~300行 |
| 配置复杂度 | 高 | 低 |

## ⚠️ 注意事项

1. **时间设置**：确保签到和评论的时间窗口不冲突
2. **评论内容**：建议使用有意义的评论内容，避免被识别为垃圾信息
3. **浏览器兼容性**：建议使用 Chrome/Edge/Firefox 最新版本
4. **页面刷新**：脚本会在早八前1分钟自动刷新页面，确保状态同步

## 📄 许可证

本脚本仅供学习交流使用，请遵守相关网站的使用条款。

## 🆘 技术支持

如遇问题，请检查：
1. 浏览器控制台错误信息
2. Tampermonkey 脚本状态
3. 时间窗口配置是否正确
4. localStorage 中是否有异常数据

---

**版本**: 1.0.0  
**更新日期**: 2026-01-31
