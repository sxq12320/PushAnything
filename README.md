# 一键投稿

Markdown 写文章，一键上传到 **公众号 / 知乎 / 头条** 三个平台的草稿箱（只进草稿，不发布）。
也支持**视频投稿**（知乎 / 头条）。

## 安装

- **安装版**（推荐）：运行 `一键投稿_Setup_x.x.x.exe`，装到 `%LOCALAPPDATA%\Programs\一键投稿`，
  自带开始菜单/桌面快捷方式和卸载程序，无需管理员权限
- **绿色版**：直接运行 `一键投稿.exe`，数据保存在 exe 同级目录（可在 设置→数据存储 里改到任意位置）

两种方式的写作数据都可通过「数据存储」设置迁移到自定义目录。

## 使用

安装版从开始菜单/桌面启动；绿色版双击 `一键投稿.exe`。

### 页面结构

侧栏顶部导航分三个页面：

- **撰写**：写文章的纯写作环境（编辑器 + 平台预览 + 保存/飞书备份）
- **发布**：选一篇文章 → 勾选平台 → 上传到草稿箱（左侧文章列表点哪篇发哪篇）
- **视频**：视频投稿表单（知乎/头条），侧栏切换为「最近任务」列表

### 首次使用

1. 点底部「登录/检查 知乎」「登录/检查 头条」→ 弹出 Edge 窗口，扫码或密码登录一次
   （登录态保存在 `profiles\` 目录，之后永久有效）
2. 公众号无需登录，走官方草稿 API（凭证读 `C:\Users\33836\media\wx_config.json`）

### 写文章

- 左侧管理已保存的文章；标题必填，作者默认「人间旁听生」，摘要可空
- **目录管理**：侧栏「目录」+ 号建文件夹；右键文件夹可重命名/删除（文章自动挪回未分类）；
  文章行悬停 ⋯ 或右键 → 移动到文件夹 / 删除 / 打开飞书文档
- **排版主题**：预览栏右上角可切换公众号样式（经典红/藏青蓝/松绿/暖橙/墨黑），
  随文章保存，上传时生效；设置里可改默认主题
- 正文用 Markdown：`**加粗**`、`*斜体*`、`## 小节`、列表、`> 引用`、表格、代码块
- **数学公式**：行内 `$E=mc^2$`、独立成段 `$$ \int_0^1 x^2\,dx = \frac{1}{3} $$`
  - 编辑器内 KaTeX 即时渲染（本地资产，离线可用）
  - 公众号/知乎/头条：公式转高清 PNG 走图片管道（本地 mathtext 渲染，断网可用；
    复杂语法如 `\begin{aligned}` 自动走 codecogs 在线渲染兜底）
  - 飞书备份：保留 LaTeX 源码，飞书文档中可手动转为公式块
- 图片：`![说明](D:\pics\a.png)` 本地图 或 `![说明](https://...)` 网络图
  - 公众号：自动上传为微信素材
  - 知乎/头条：自动通过编辑器上传按钮插入
- 表格：三个平台统一渲染成图片插入（编辑器粘贴表格必乱）
- 封面（公众号必填）：点「选图」手动选，留空则按标题自动生成深蓝渐变封面

### 编辑器（Typora 式手感）

- **即时渲染**：边写边排版，光标行才显示标记符号；打字机模式保持行居中
- **快捷键**：`Ctrl+B` 加粗 · `Ctrl+I` 斜体 · `Ctrl+K` 链接 · `Ctrl+E` 行内代码 ·
  `Ctrl+Shift+K` 代码块 · `Ctrl+Shift+M` 行内公式 · `Ctrl+T` 表格 · `Alt+Shift+5` 删除线 · `Ctrl+S` 保存
- **智能输入**：选中文字后敲 `*` `_` `` ` `` `~` `$` 直接包裹；选中文字后粘贴网址自动生成 `[文字](网址)`
- **粘贴图片**：剪贴板图片直接 Ctrl+V，自动存到文章 `assets/` 目录并插入相对路径
- **大纲**：工具栏末尾「☰」按钮弹出标题大纲，点击跳转
- **自动保存**：已保存过的文章停笔 15 秒自动落盘（不触发飞书备份）
- 支持 `==高亮==`、脚注 `[^1]`、`[TOC]` 目录标记、自动空格

### 发布文章

撰写页点「去发布」，或导航点「发布」→ 左侧列表选文章 → 勾选平台 → 「上传到草稿箱」。
三个平台依次执行，日志区显示进度。发布页可覆盖主题/封面设置。

### 视频投稿

导航点「视频」：点虚线框选视频文件 → 填标题/简介 →（可选封面图）→ 勾选知乎/头条 → 上传。
公众号置灰是因为图文草稿接口不支持纯视频（视频号是另一套体系）。
侧栏「最近任务」显示所有投稿记录，点任务可看完整日志。
找不到「存草稿」按钮的平台会填好内容后**保留浏览器窗口**由你手动发布。
知乎/头条会弹出 Edge 窗口自动填稿（知乎自动存草稿，头条点「存草稿」），
窗口中出现验证码时手动过一下即可。正式发布在各平台后台手动操作。

## 飞书备份

把文章同步为飞书云文档。点侧栏「⚙ 设置」→「飞书备份」配置，或点「☁ 备份」手动备份当前文章。

### 开通步骤（一次性，约 5 分钟）

1. 打开 [open.feishu.cn](https://open.feishu.cn) → 「开发者后台」→ 创建**企业自建应用**，拿到 `App ID` 和 `App Secret`
2. 应用管理 → 「权限管理」→ 搜索并开通云文档相关权限（建议全选）：
   `docx:document`、`drive:drive`、`drive:file`、`docs:doc`、**导入云文档**（drive:import）
3. 「版本管理与发布」→ 创建版本并发布（个人/自建租户一般自动通过）
4. 飞书客户端 → 云文档 → 新建一个文件夹（如「文章备份」）→
   右上角「···」→ 添加文档应用/协作者 → 搜索你的应用名加为**可编辑**协作者
5. 打开该文件夹，浏览器地址栏 `folder/xxxxxxxx` 最后一段就是**文件夹 Token**
6. 三项填进设置页 → 「测试连接」→ 勾选「保存文章时自动备份」→ 保存设置

### 备份行为

- **保存文章时自动备份**（开启后）；「☁ 备份」按钮随时手动备份
- 每次备份用飞书官方 Markdown 导入生成新版云文档，并自动**删除该文旧版本**（不堆积重复文档）
- 已备份的文章在列表中带 ☁ 标记
- API 投递的图文任务也会自动备份（无需传额外参数）
- 也可单独调 `POST /api/feishu`：`{"title":..,"md":..,"wait":true}`

## 本地 API（给其他软件/脚本调用）

软件运行时自动启动本地接口：`http://127.0.0.1:8737/api`（仅本机，端口可在 `config.json` 改 `api_port`，`api_enabled:false` 关闭，`api_token` 设置后请求需带 `X-Token` 头）。
侧栏底部会显示 API 运行状态。也可无窗口纯服务运行：`一键投稿.exe --serve`

### 接口

```
GET  /api              接口说明
GET  /api/health       存活检查
GET  /api/tasks        最近任务列表
GET  /api/tasks/{id}   任务详情（status / logs / results）

POST /api/article      图文投稿
  { "title": "标题",                      // 必填
    "md": "# markdown正文",               // 必填
    "author": "作者", "digest": "摘要",    // 可选
    "cover_path": "D:\\封面.png",          // 可选，缺省自动生成
    "platforms": ["wechat","zhihu","toutiao"],
    "wait": true }                        // 可选，同步等结果

POST /api/video        视频投稿（框架已就绪，处理器逐步适配）
  { "title": "标题", "video_path": "D:\\a.mp4",   // 必填
    "desc": "简介", "cover_path": "封面",          // 可选
    "platforms": ["toutiao","zhihu"], "wait": true }

POST /api/feishu       飞书云文档备份
  { "title": "标题", "md": "markdown正文",         // 必填
    "slug": "文章slug",                            // 可选，回写本地meta并替换旧备份
    "wait": true }
```

返回：`{"ok":true,"task_id":"xxx"}` 异步任务；`wait:true` 时返回完整结果。

### 调用示例

```bash
curl -X POST http://127.0.0.1:8737/api/article ^
  -H "Content-Type: application/json" ^
  -d "{\"title\":\"测试\",\"md\":\"## 你好\",\"platforms\":[\"wechat\"],\"wait\":true}"
```

```python
import requests
r = requests.post("http://127.0.0.1:8737/api/article", json={
    "title": "文章标题", "md": md_text,
    "platforms": ["wechat", "zhihu", "toutiao"], "wait": True,
}, timeout=600)
print(r.json()["task"]["results"])
```

### 视频投稿说明

- 视频任务走同一队列，按平台分发到 `zhihu_video.py` / `toutiao_video.py` 处理器
- 视频类平台草稿机制不统一：能点「存草稿」就存，找不到入口则**填好内容后保留浏览器窗口**，由你手动点发布（不替你发布）
- 公众号图文接口不支持纯视频稿；视频号另算
- 新平台/新内容类型：在 `runner.py` 注册 handler 即可接入

## 目录说明（exe 旁边）

| 目录/文件 | 内容 |
|---|---|
| `drafts\` | 本地保存的文章（.md + .json 元信息 + assets\ 粘贴图） |
| `profiles\zhihu` `profiles\toutiao` | 浏览器登录态，删除即退出登录 |
| `assets\` | 生成的封面、上传完成截图 |
| `history.json` | 投稿记录（上限 200 条） |
| `config.json` | 作者名、凭证路径、数据目录等配置（固定在 exe 旁） |
| `crash.log` | 崩溃日志（出错时排查用） |

> **自定义数据位置**：设置 →「数据存储」→ 更改，可把 `drafts\ profiles\ assets\ history.json` 整体迁到任意目录（如 D:\我的数据），迁移自动完成，重启生效。`config.json` 始终留在 exe 旁。

## 开发

```bat
:: 环境
python -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt

:: 打包绿色 exe
build.bat

:: 打包绿色 exe + 安装程序（需 Inno Setup 6）
build_installer.bat
```

发布流程：推一个 `v*` 标签，GitHub Actions 自动构建 exe + 安装包并创建 Release。

## License

MIT © 一键投稿 contributors

源码在 `app\`：`main.py` 入口、`backend.py` 前后端桥、`mdconvert.py` Markdown转换、
`wechat_push.py` 公众号API、`zhihu_push.py`/`toutiao_push.py` 浏览器自动化、`browser.py` 自动化工具、
`feishu_sync.py` 飞书云文档备份、`jobs.py` 任务队列、`api_server.py` 本地HTTP接口。

## 已知说明

- 知乎/头条没有官方草稿接口，靠浏览器自动化实现；平台改版可能导致选择器失效，需更新 `zhihu_push.py` / `toutiao_push.py` 顶部的选择器列表
- 上传时弹出的 Edge 窗口不要手动关闭，等它自己关
- exe 约 60MB（内置 Python + Playwright 驱动），首次启动需解压几秒
