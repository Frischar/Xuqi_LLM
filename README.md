# Xuqi LLM Chat

<p align="center">
  <img src="./assets/preview.png" alt="Xuqi LLM Chat WebUI Preview" width="80%">
</p>

## 附属工具

仓库根目录现已包含一个独立工具：

- [worldbook maker](./worldbook%20maker)

它是一个面向制作者的世界书整理与生成 WebUI，用来把自然语言设定素材整理成 Xuqi 风格的世界书 JSON。

直接双击：

- `worldbook maker/启动webui.bat`

即可在本地浏览器中启动工具页面。


一个本地运行的 AI 伴侣聊天项目，基于 `FastAPI + WebUI` 构建，支持角色卡、记忆库、世界书、预设、差分立绘、创意工坊和桌面启动器。

Made by `Frischar` and `manbo`

本项目当前仍在持续完善中。  
如在使用过程中遇到问题，欢迎提交 Issue 进行反馈与交流。

开发过程使用 AI（`AI coding`）辅助完成。

## 现在的项目状态

- `/` 会直接跳转到 `/chat`
- 当前运行数据以全局方式管理
- 人设卡可以随时加载
- 记忆、世界书、预设都支持独立导入导出
- 设置页支持把“当前人设卡 + 记忆 + 世界书 + 预设”打包导出为一个 ZIP

## 最近更新

- 重构了底层代码结构：页面路由、配置接口、聊天接口、数据模型、世界书逻辑和创意工坊逻辑都从 `app.py` 中拆出
- 运行时数据改为全局管理，不再以旧的多存档槽位为主
- 补充了记忆、世界书、预设的独立导入导出能力
- 设置页新增“当前人设卡 + 记忆 + 世界书 + 预设”组合包导出
- 聊天页新增 Prompt 打包预览，能直接查看当前轮注入了哪些上下文
- 移除了旧欢迎页，首页现在直接进入聊天页

## 项目特点

- 本地 WebUI，开箱即用
- OpenAI 兼容聊天接口
- 流式输出
- 角色卡导入、编辑、导出、热切换
- 记忆库独立维护，支持导入导出
- 世界书设置页与词条管理页，支持按需触发
- 预设独立管理，支持导入导出与一键切换
- 差分立绘与角色头像
- 背景图、主题、透明度等界面设置
- 创意工坊规则、阶段推进与资源上传
- 聊天侧栏可预览本轮 Prompt 打包结果
- 可选接入嵌入模型与重排序模型
- 支持封包为桌面启动器

## 页面入口

- `/chat`
  主聊天页
- `/config`
  常规配置页
- `/config/preset`
  预设管理页
- `/config/user`
  用户资料页
- `/config/card`
  角色卡页
- `/config/workshop`
  创意工坊页
- `/config/memory`
  记忆库页
- `/config/worldbook`
  世界书设置页
- `/config/worldbook/entries`
  世界书词条管理页
- `/config/sprite`
  立绘管理页

## 快速启动

### 方式一：双击启动

直接双击：

`启动webui.bat`

脚本会自动：

- 检测是否已安装 Python
- 检测 Python 版本是否至少为 `3.10`
- 首次运行时创建 `.venv`
- 安装依赖
- 启动本地 WebUI

如果没有安装 Python，脚本会给出提示，并打开官方下载页面。

### 方式二：命令行启动

```powershell
cd "E:\AI chat 项目\Xuqi_LLM"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

然后打开：

`http://127.0.0.1:8000`

## 基本使用

### 1. 配置聊天模型

在 `Config` 页填写：

- `API URL`
- `API Key`
- `Model`

只要接口兼容 OpenAI Chat Completions 风格，就可以直接接入。

### 2. 加载角色卡

角色卡本身是独立的人设资产，可以从 `cards/` 目录读取，也可以在页面里导入、编辑和导出。

当前默认模板：

- [cards/template_role_card.json](./cards/template_role_card.json)

### 3. 管理记忆、世界书和预设

- 记忆库：在 `/config/memory` 维护，可独立导入导出
- 世界书：在 `/config/worldbook` 和 `/config/worldbook/entries` 维护，可独立导入导出
- 预设：在 `/config/preset` 维护，可独立导入导出

设置页还可以直接导出当前整套组合包：

- 当前角色卡
- 当前记忆
- 当前世界书
- 当前预设

### 4. 可选的检索增强

可以额外配置：

- 嵌入模型
- 重排序模型

未配置时，主聊天功能仍可正常运行，只是不会启用对应的检索增强链路。

### 5. Prompt 预览

聊天页侧栏支持查看当前轮的 Prompt 打包结果，方便排查：

- 系统提示
- 角色卡设定
- 记忆与长期信息
- 世界书命中内容
- 最近聊天记录
- 本轮用户输入

## 封包与启动器

项目支持封包为单文件桌面启动器。

可使用：

`封包器.bat`

封包后的启动器会：

- 启动本地服务
- 自动打开独立窗口
- 关闭窗口后退出程序

运行数据会优先生成在 `exe` 同目录，例如：

- `data/`
- `cards/`
- `static/`
- `exports/`
- `browser_profile/`

如果当前目录没有写权限，才会回退到系统用户目录。

## 目录结构

```text
.
|-- app.py
|-- app_models.py
|-- page_routes.py
|-- config_api_routes.py
|-- chat_api_routes.py
|-- worldbook_logic.py
|-- workshop_logic.py
|-- slot_runtime.py
|-- launcher.py
|-- preset_rules.py
|-- requirements.txt
|-- README.md
|-- LICENSE
|-- 启动webui.bat
|-- 封包器.bat
|-- app_icon.ico
|-- cards/
|   `-- template_role_card.json
|-- data/
|-- templates/
|   |-- index.html
|   |-- config.html
|   |-- preset.html
|   |-- user_config.html
|   |-- card_config.html
|   |-- workshop_config.html
|   |-- memory_config.html
|   |-- sprite_config.html
|   |-- worldbook_config.html
|   `-- worldbook_manager.html
`-- static/
    |-- styles.css
    |-- uploads/
    `-- sprites/
```

## 开发入口

- 应用启动与共享核心逻辑：`app.py`
- 页面路由：`page_routes.py`
- 配置相关 API：`config_api_routes.py`
- 聊天相关 API：`chat_api_routes.py`
- 数据模型：`app_models.py`
- 世界书逻辑：`worldbook_logic.py`
- 创意工坊逻辑：`workshop_logic.py`
- 页面模板：`templates/`
- 样式文件：`static/styles.css`

## 开源协议

本项目基于 GPL-3.0 许可证开源。

在使用、修改和分发本项目代码时，请遵守相应开源许可条款。

## 免责声明

本项目仅提供本地部署工具与开源源码，不提供任何在线模型服务、账号注册、托管或运营支持。

用户需自行配置第三方模型接口，并自行承担由此产生的合规、隐私、安全及使用责任。使用本项目时，请遵守所在地法律法规及相关第三方服务条款。

请勿将本项目用于生成、传播或存储任何违法违规内容，包括但不限于色情低俗、血腥暴力、未成年人不当内容、侵害他人合法权益或其他法律法规禁止的信息。

本项目开发者不对使用者基于本项目进行的二次部署、接口接入、内容生成或衍生用途承担责任。
