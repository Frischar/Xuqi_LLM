# Xuqi LLM Chat

<p align="center">
  <img src="./assets/preview.png" alt="Xuqi LLM Chat WebUI Preview" width="80%">
</p>
一个本地运行的 AI 伴侣聊天项目，基于 `FastAPI + WebUI` 构建，支持多存档、角色卡、世界书、记忆库、差分立绘和桌面启动器。

本项目仅提供本地工具与源码
不提供在线模型服务
用户自行配置第三方接口并自行承担相应合规与隐私责任
请勿用于违法违规内容生成

Made by `Frischar`and`manbo`

第一次搞这种东西....做的不好见谅

使用`AI coding`制作

## 更新日志v1.1

- 补充了世界书相关页面入口：
  - `/config/worldbook`
  - `/config/worldbook/entries`
- 补充了角色卡模板说明，默认只保留：
  - `cards/template_role_card.json`
- 补充了双击启动脚本的 Python 检测说明：
  - 会检查是否安装 Python
  - 会检查版本是否至少为 `3.10`
  - 未安装时会给出下载提示
- 补充了“未配置嵌入模型 / 重排序模型时仍可正常聊天”的说明。

## 项目特点

- 本地 WebUI，开箱即用
- 多存档隔离
- 角色卡导入、编辑、导出
- 世界书设置页与词条管理页
- 可编辑记忆库
- 差分立绘与表情标签切换
- 背景图、主题、透明度等界面设置
- OpenAI 兼容聊天接口
- 可接入嵌入模型与重排序模型
- 流式输出
- 可封包为桌面启动器

## 页面入口

- `/`
  欢迎页
- `/chat`
  主聊天页
- `/config`
  常规配置页
- `/config/card`
  角色卡配置页
- `/config/memory`
  记忆库配置页
- `/config/sprite`
  立绘管理页
- `/config/worldbook`
  世界书设置页
- `/config/worldbook/entries`
  世界书词条管理页

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
cd "G:\xuqi_llm聊天_github"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

然后打开：

`http://127.0.0.1:8000`

## 使用说明

### 聊天模型

在 `Config` 页填写：

- `API URL`
- `API Key`
- `Model`

只要接口兼容 OpenAI Chat Completions 风格，就可以直接接入。

### 嵌入模型与重排序

可选接入：

- 嵌入模型
- 重排序模型

未配置时，主聊天功能仍可正常运行，只是不会启用检索增强链路。

### 存档机制

默认提供 3 个存档槽位：

- `slot_1`
- `slot_2`
- `slot_3`

每个槽位独立保存：

- 人设
- 聊天记录
- 记忆库
- 世界书
- 当前角色卡
- 立绘目录
- 部分本地运行时配置

立绘默认按槽位读取：

- `/static/sprites/slot_1`
- `/static/sprites/slot_2`
- `/static/sprites/slot_3`

### 角色卡

支持：

- 从 `cards/` 目录加载角色卡
- 在页面内编辑角色卡
- 导出当前角色卡

仓库默认只保留一张模板角色卡：

- [cards/template_role_card.json](./cards/template_role_card.json)

## 封包与启动器

项目支持封包为单文件桌面启动器。

可使用：

`封包器.bat`

封包后的启动器行为：

- 单个 `exe` 启动
- 自动拉起本地服务
- 自动打开独立窗口
- 关闭窗口后程序退出

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
|-- launcher.py
|-- requirements.txt
|-- README.md
|-- 启动webui.bat
|-- 封包器.bat
|-- app_icon.ico
|-- cards/
|   `-- template_role_card.json
|-- data/
|   |-- persona.json
|   |-- settings.json
|   |-- save_slots.json
|   `-- slots/
|-- templates/
|   |-- welcome.html
|   |-- index.html
|   |-- config.html
|   |-- card_config.html
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

- 后端主入口：`app.py`
- 桌面启动器入口：`launcher.py`
- 页面模板：`templates/`
- 样式文件：`static/styles.css`
