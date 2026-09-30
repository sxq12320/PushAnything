<div align="center">
  <img src="installer/icon.png" width="96" alt="PushAnything">
  <h1>PushAnything</h1>
  <p><b>一处写作 · 处处发布</b></p>
  <p>Markdown 写一次，一键投递到 <b>公众号 / 知乎 / 头条</b> 草稿箱；也支持<b>视频投稿</b>与<b>飞书备份</b>。<br>
  只进草稿箱，正式发布永远由你自己点。</p>
  <p>
    <img src="https://img.shields.io/badge/platform-Windows%2010%2B-0078D4?style=flat-square" alt="platform">
    <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?style=flat-square" alt="python">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="license">
  </p>
</div>

---

## 功能一览

| | |
|---|---|
| 📝 **写作工作台** | IR 即时渲染 / Markdown 源码、专注模式、快捷键、大纲导航、1.2s 自动保存与恢复副本 |
| ∑ **数学公式** | KaTeX 即时渲染；发布时转高清 PNG 走图片管道（本地 mathtext，断网可用） |
| 🎨 **排版与写作模板** | 旷野 / 经典红 / 藏青蓝 / 松绿 / 暖橙 / 墨黑；内置文章结构，支持保存自己的模板 |
| 🗂 **目录管理** | 文件夹、搜索、右键菜单、移动归档 |
| 📤 **多平台投递** | 公众号走官方草稿 API；知乎/头条走 Edge 自动化（登录态持久化） |
| 🎬 **视频投稿** | 知乎 / 头条视频草稿，独立页面与任务队列 |
| ☁️ **飞书备份** | 保存即同步为飞书云文档，自动清理旧版本 |
| 📜 **投稿记录** | B 站稿件管理式历史列表，逐平台结果徽标，`history.json` 重启不丢 |
| 🔌 **本地 API** | `http://127.0.0.1:8737/api`，其他软件/脚本可直接投递任务 |
| 📱 **手机端** | 同一 WiFi 下手机扫码打开网页，写稿/选稿/看任务进度，投稿由电脑执行 |
| 💾 **自定义数据目录** | 所有本地数据可整体迁移到任意位置 |

## 截图

<p align="center">
  <img src="docs/screenshot-home.png" width="31%" alt="首页">
  <img src="docs/screenshot-write.png" width="31%" alt="撰写">
  <img src="docs/screenshot-publish.png" width="31%" alt="发布">
</p>

## 安装

去 [Releases](../../releases) 下载最新版：

- **安装版**（推荐）：`PushAnything_Setup_x.x.x.exe` —— 装到 `%LOCALAPPDATA%\Programs\PushAnything`，
  开始菜单/桌面快捷方式 + 卸载程序，无需管理员权限
- **绿色版**：`PushAnything.exe` —— 放任意目录双击即用，数据存 exe 同级目录

## 快速开始

1. **登录一次**：侧栏底部「知乎登录」「头条登录」→ 弹出的 Edge 窗口里扫码/密码登录，
   登录态存在 `profiles\` 目录长期有效。公众号走官方 API，无需登录
2. **公众号凭证**：设置 →「公众号」→ 选择凭证 JSON（含 `mp_appid` / `mp_appsecret` 字段，
   在公众号后台 → 设置与开发 → 基本配置中获取；需开启「草稿箱」相关接口权限）
3. **写作**：撰写页直接写，也可从模板开始；无标题稿可以自动保存，投递前补上标题。选目录、配主题、贴封面（留空自动生成渐变封面）
4. **投递**：点「去发布」→ 勾选平台 →「上传到草稿箱」，日志区看实时进度

## 页面

侧栏导航分四个页面：

- **首页**：问候语 + 快捷操作 + 最近文章卡片墙（卡片色条跟随排版主题），点卡片直接续写
- **撰写**：纯写作环境——标题、作者/摘要/封面、编辑器 + 平台实时预览、日志
- **发布**：选文章 → 平台胶囊 → 上传；下方是投稿记录面板，点条目展开完整日志
- **视频**：视频选择卡 + 标题/简介/封面 → 知乎/头条；侧栏切换为「最近任务」

## 编辑器细节（Typora 手感）

- 快捷键：`Ctrl+B` 加粗 · `Ctrl+I` 斜体 · `Ctrl+K` 链接 · `Ctrl+E` 行内代码 ·
  `Ctrl+Shift+K` 代码块 · `Ctrl+Shift+M` 行内公式 · `Ctrl+T` 表格 · `Alt+Shift+5` 删除线 · `Ctrl+S` 保存
- 选中文字敲 `*` `_` `` ` `` `~` `$` 直接包裹；选中文字后粘贴网址自动生成 `[文字](网址)`
- 剪贴板图片 `Ctrl+V` 自动存到文章 `assets/` 目录并插入相对路径
- 工具栏末尾 ☰ 弹出标题大纲，点击跳转
- `Ctrl+Alt+M` 切换写作与 Markdown 源码；专注模式收起周边面板，按 Esc 返回
- 支持 `==高亮==`、脚注 `[^1]`、`[TOC]`、中英文自动空格

### 旷野 · 野生观察

纸色底、墨黑大标题、锈红重点句，偏向有锋芒的独立刊物。正文从具体场景和追问展开，用有依据的判断推动阅读。段落可以删改，无需每篇套用同一结构。

在「撰写 → 模板」选择「旷野 · 野生观察」，可切换查看正文骨架和排版效果。
仓库提供[可复用骨架](docs/templates/wild/template.md)、[完整示例](docs/templates/wild/example.md)和 [HTML 排版预览](docs/templates/wild/preview.html)；Release 同时提供模板文件包。

## 数学公式

- 行内 `$E=mc^2$`，独立成段 `$$ \int_0^1 x^2\,dx = \frac{1}{3} $$`
- 编辑器内 KaTeX 即时渲染（**本地资产，离线可用**）
- 发布时：公式转 220dpi 透明 PNG 走图片管道——本地 **matplotlib mathtext** 渲染（断网可用），
  复杂语法（`\begin{aligned}` 等）自动降级到 codecogs 在线渲染，再兜底源码文本，永不空白
- 飞书备份保留 LaTeX 源码，可在飞书文档中手动转为公式块

## 图片与表格

- 图片：`![说明](D:\pics\a.png)` 本地图 或 `![说明](https://...)` 网络图
  - 公众号：自动上传为微信素材；知乎/头条：模拟编辑器上传按钮按位置插入
- 表格：三平台统一渲染成图片插入（富文本编辑器粘贴表格必乱）

## 飞书备份

保存文章时自动同步为飞书云文档（官方 Markdown 导入接口，排版完整保留），或点工具栏 ☁ 手动备份。
已备份文章带云标记，右键可「在飞书中打开」；重复备份自动替换旧文档。

**一次性配置（约 5 分钟）**：

1. [open.feishu.cn](https://open.feishu.cn) → 开发者后台 → 创建**企业自建应用**，拿到 `App ID` / `App Secret`
2. 权限管理 → 开通 `docx:document`、`drive:drive`、`drive:file`、`docs:doc`、导入云文档
3. 版本管理与发布 → 创建版本并发布
4. 飞书客户端建文件夹 → 把应用加为**可编辑**协作者 → 文件夹 URL 最后一段是 Token
5. 三项填进设置页 →「测试连接」→ 勾选「保存文章时自动备份」

## 本地 API

软件运行时自动启动 `http://127.0.0.1:8737/api`（仅本机）。
设置里可改端口/关闭/设 `api_token`（设置后请求需带 `X-Token` 头）。
也可无窗口纯服务运行：`PushAnything.exe --serve`

```
GET  /api              接口说明          GET  /api/tasks/{id}  任务详情
GET  /api/health       存活检查
GET  /api/tasks        最近任务列表
GET  /api/articles     已保存文章列表（手机端用）
GET  /m                手机端页面（不鉴权）

POST /api/article      图文投稿
  { "title": "标题", "md": "# 正文",                 // 必填
    "author": "", "digest": "", "cover_path": "",     // 可选
    "style": "blue",                                  // 可选，公众号主题
    "platforms": ["wechat","zhihu","toutiao"],
    "wait": true }                                    // 同步等结果

POST /api/video        视频投稿
  { "title": "", "video_path": "D:\\a.mp4",           // 必填
    "desc": "", "cover_path": "",                     // 可选
    "platforms": ["toutiao","zhihu"], "wait": true }

POST /api/feishu       飞书云文档备份
  { "title": "", "md": "", "slug": "", "wait": true }
```

```bash
curl -X POST http://127.0.0.1:8737/api/article ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"测试\",\"md\":\"## 你好\",\"platforms\":[\"wechat\"],\"wait\":true}"
```

## 手机端

手机不需要装任何 App——电脑上的 API 服务同时提供一个局域网网页：

1. 电脑和手机连**同一 WiFi**
2. 打开 PushAnything → 设置 →「手机端」→ **扫二维码**（或手动输入显示的网址 `http://电脑IP:端口/m`）
3. 首次连接 Windows 可能弹防火墙提示，选"允许专用网络"
4. 设置了 `api_token` 的话，手机端首次打开填一次 Token（会记住）

手机端三个页签：

- **写稿**：标题 + Markdown 正文 + 作者/摘要，选平台直接投递
- **选稿**：列出电脑上已保存的文章，点选后一键投递
- **任务**：实时任务进度（5 秒自动刷新），点任务可展开日志

所有投稿实际由电脑端的浏览器执行，手机只是个遥控器——所以**电脑必须开着 PushAnything**。
不想让局域网访问时，在设置里取消勾选「允许局域网访问」即可（重启生效）。

## 窗口操作

无边框窗口，支持以下操作：

- **拖标题栏到屏幕边缘**：顶部→最大化，左右缘→半屏，角落→四分屏（系统 Aero Snap）
- **最大化时拖标题栏**：先还原到光标下再继续拖
- **拖任意边缘/角落**自由缩放（初始最小 720×520）；标题栏双击 = 最大化/还原
- **右键标题栏**：左半屏 / 右半屏 / 上半屏 / 最大化快捷菜单

## 数据目录

| 目录/文件 | 内容 |
|---|---|
| `drafts\` | 文章（`.md` + `.json` 元信息 + `assets\` 粘贴图），支持子文件夹 |
| `profiles\` | 知乎/头条浏览器登录态，删除即退出 |
| `assets\` | 生成的封面、截图 |
| `history.json` | 投稿记录（上限 200 条） |
| `templates.json` | 自定义写作模板 |
| `.draft-recovery.json` | 尚未完成保存的编辑恢复副本 |
| `config.json` | 配置（固定在 exe 旁，内含数据目录指针） |
| `crash.log` | 崩溃日志 |

> 设置 →「数据存储」可安排下次启动时迁移数据。软件复制数据、更新本地图片路径后再切换目录；原目录保留。

## 开发

```bat
:: 环境
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt

:: 绿色 exe
build.bat

:: 绿色 exe + 安装包（需 Inno Setup 6）
build_installer.bat

:: 重新生成应用图标
venv\Scripts\python.exe make_icon.py
```

推 `v*` 标签触发 GitHub Actions：自动构建 exe + 安装包并创建 Release。

### 结构

```
app/
  main.py          入口（pywebview 窗口）
  backend.py       前后端桥（JS API）
  api_server.py    本地 HTTP API
  jobs.py          统一任务队列（UI 与 API 共用）
  runner.py        任务分发：article / video / feishu → 各平台 handler
  mdconvert.py     Markdown → 各平台 HTML（含公式/表格/主题渲染）
  wechat_push.py   公众号官方草稿 API
  zhihu_push.py    知乎浏览器自动化     zhihu_video.py   知乎视频
  toutiao_push.py  头条浏览器自动化     toutiao_video.py 头条视频
  feishu_sync.py   飞书云文档备份
  web/             前端（Vditor IR + KaTeX，全部本地化离线可用）
```

新增内容类型/平台：在 `runner.py` `register(kind, fn)` 一行接入，队列/日志/历史/API 自动继承。

## 已知说明

- 知乎/头条无官方草稿接口，靠浏览器自动化；平台改版可能导致选择器失效，
  需更新 `*_push.py` / `*_video.py` 顶部的选择器列表
- 上传时弹出的 Edge 窗口不要手动关闭；出现验证码手动过一下即可
- 找不到「存草稿」入口的平台会填好内容后保留窗口，由你手动点发布
- exe 约 90MB（内置 Python + Playwright + matplotlib），首次启动需解压几秒

## 更新日志

**v1.3.0 · 写作工作台**
- 新增「旷野 · 野生观察」排版与文章结构模板，纸色底、墨黑标题、锈红标记；模板可切换排版效果与正文骨架
- 内置深度长文、产品测评、研究笔记、图文教程，可把自己的正文与图片保存为模板
- 写作 / Markdown 源码切换、专注模式、隐藏预览、收起活动日志，适配 720×520 起的小窗口和减少动态效果的系统偏好
- 停笔 1.2 秒自动保存，新建无标题稿也能保存；持续写作最多每 10 秒保存一次；切稿和退出前保存，保存中继续输入不会误清未保存状态
- 未保存内容额外写入恢复副本，异常退出后恢复为独立新稿，保留原文章
- 图片选择、粘贴、拖入统一导入：修正 EXIF 方向，长边上限 2560 像素，保留原图、透明通道和 GIF 动画；相同图片去重
- 同名稿与移动归档不覆盖已有文章，移动时带上图片；删除进入 `.trash`，界面提供撤销
- 上传区分成功、部分失败、失败、待人工检查；重试只提交失败平台，排队任务可取消；任务日志不再阻塞工作线程
- 实时预览隔离于沙盒，防止文章 HTML 调用桌面桥；网络配图不再由预览反复下载，公式和表格缓存渲染结果
- 数据目录改为下次启动复制迁移，更新图片路径并保留原数据；新配置默认关闭局域网访问，手机端可在设置中开启
- 修复历史任务重启后无法查询、手机选稿图片基准路径、路径净化与 API 参数校验等问题

开发验证：`venv\Scripts\python.exe -m unittest discover -s tests -v`；`tests/ui_smoke.py` 使用 Edge 与隔离数据验证界面，`tests/native_smoke.py` 验证真实 WebView2 桥接。测试不连接真实投稿平台。

**v1.2.0**
- 新增手机端：同 WiFi 扫码打开网页，写稿/选稿/看任务（电脑执行投稿）
- 标题栏拖动接入系统原生移动循环：拖到屏幕边缘自动 Snap（顶部全屏、左右半屏、角落四分屏）
- 公众号引用样式改为浅彩圆角色块；修复引用内容丢失的 bug
- 编辑区悬停显示 I 型光标

**v1.0.0**
- 首个公开版本

## License

[MIT](LICENSE) © PushAnything contributors
