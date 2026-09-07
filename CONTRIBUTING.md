# 贡献指南

感谢你考虑为 **彼岸桌面壁纸浏览器（NetBianWallpaper）** 贡献代码或反馈问题！这是一个个人开源的 Windows 壁纸浏览器，采用 Fluent / WinUI 风格界面，数据来源于彼岸图网。

无论你是想报告 Bug、提建议，还是直接提交代码，都欢迎。下面是一些简单的约定，帮助你快速上手。

---

## ⭐ 支持项目

如果你觉得这个项目对你有帮助，最直接的支持方式是：

- **点一个 Star**：在仓库主页右上角点击 ⭐ **Star**，让更多人看到它；
- **Fork**：右上角 **Fork** 到自己的账号，随时基于它做二次开发；
- **分享**：把项目推荐给需要的人。

> Star 数越多，项目在 GitHub 上的曝光度越高，也会激励我持续维护。谢谢！

---

## 🐛 反馈问题（Issue）

在提交 Issue 前，请先搜索一下是否已有相同问题，避免重复。

提交时尽量包含以下信息，能帮我更快定位：

- **运行环境**：Windows 版本、Python 版本（源码运行）或 EXE 版本；
- **复现步骤**：清晰描述「做了什么 → 期望什么 → 实际发生了什么」；
- **截图 / 报错日志**：如果界面异常或程序报错，附上截图和报错堆栈；
- **触发条件**：是否与某个分类、某张壁纸、某种主题模式相关。

问题分类建议：

| 标签 | 用途 |
|---|---|
| `bug` | 程序错误、崩溃、显示异常 |
| `enhancement` | 功能建议、改进想法 |
| `question` | 使用上的疑问 |

---

## 🛠 贡献代码（Pull Request）

### 1. 环境准备

```bash
# 克隆你的 fork
git clone https://github.com/<你的用户名>/NetBianWallpaper.git
cd NetBianWallpaper

# 安装依赖
pip install PySide6 PySide6-Fluent-Widgets Pillow requests
# 可选：更稳的 TLS 指纹模拟
pip install curl_cffi
```

### 2. 创建分支

```bash
git checkout -b feat/你的功能名   # 或 fix/你修复的问题
```

### 3. 开发与验证

```bash
# 运行程序
python wallpaper.py
# 直接跳到设置页
python wallpaper.py --settings
```

提交前请确保：

- `python -m py_compile wallpaper.py` 通过；
- 改动不破坏已有功能（尤其是磨砂玻璃、自动配色、定时切换这几块历史问题较多的模块）；
- 界面改动尽量在明、暗两套主题下都自测一遍。

### 4. 提交与推送

```bash
git add -A
git commit -m "feat: 一句话描述改动"
git push origin feat/你的功能名
```

### 5. 发起 Pull Request

在 GitHub 上从你的分支向 `jman-test/NetBianWallpaper` 的 `main` 分支发起 PR，并简要说明：

- 改了什么、为什么改；
- 如何验证（附截图更好）；
- 是否涉及需要重新打包 EXE 的界面改动。

---

## 📦 版本与发布

- 版本号遵循 **语义化版本**：`主版本.次版本.修订号`（如 `1.0.0`）；
- 源码中的版本号统一由 `wallpaper.py` 顶部的 `APP_VERSION` 常量维护，界面「关于软件」显示的版本由它自动派生；
- 发布新版本时：更新 `APP_VERSION` → 重新打包 → 打 tag（`vX.Y.Z`）→ 在 Release 中上传新 EXE。

---

## 💬 交流

有想法或问题，优先通过 GitHub **Issue** 提出，我会尽量及时回复。

再次感谢你的支持！
