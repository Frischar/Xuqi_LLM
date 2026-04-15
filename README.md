# Xuqi LLM Chat

一个基于 `FastAPI + WebUI` 的本地 AI 伴侣聊天项目，支持多存档、角色卡、世界书、记忆库、立绘切换和桌面启动器。

项目定位偏向：

- 本地运行
- 可自定义扩展
- 适合做角色陪伴、设定互动和聊天原型

使用AI coding编程制作 为测试产物

Made by `Frischar`.

## 功能概览

- 欢迎页、聊天页、配置页分离
- 多存档隔离
- 角色卡导入、编辑、导出
- 世界书关键词触发
- 可编辑记忆库
- 立绘管理与情绪切换
- 背景图、主题、透明度等界面设置
- OpenAI 兼容聊天接口
- 预留嵌入模型与重排序模型接入
- 流式输出
- 单文件桌面启动器封包

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

## 目录结构

```text
.
|-- app.py
|-- launcher.py
|-- requirements.txt
|-- README.md
|-- 启动webui.bat
|-- 封包器.bat
|-- data/
|   |-- settings.json
|   |-- persona.json
|   |-- save_slots.json
|   `-- slots/
|-- cards/
|-- templates/
|   |-- welcome.html
|   |-- index.html
|   |-- config.html
|   |-- card_config.html
|   |-- memory_config.html
|   `-- sprite_config.html
`-- static/
    |-- styles.css
    |-- uploads/
    `-- sprites/
```

## 本地启动

### 方式一：直接双击

双击：

`启动webui.bat`

它会自动创建虚拟环境、安装依赖并启动本地 WebUI。

### 方式二：命令行运行

```powershell
cd "G:\xuqi_llm聊天"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app:app --reload --host 127.0.0.1 --port 8000
```

然后打开：

`http://127.0.0.1:8000`

## 启动器与封包

项目支持封包为单文件启动器。

重新封包可运行：

`封包器.bat`

封包后的启动器行为：

- 单个 `exe` 启动
- 自动拉起本地服务
- 自动打开独立应用窗口
- 关闭窗口后程序退出

运行数据会优先生成在 `exe` 同目录，例如：

- `data/`
- `cards/`
- `static/`
- `exports/`
- `browser_profile/`

如果当前目录没有写权限，才会回退到系统本地用户目录。

## 配置说明

### 聊天模型

- `API URL`
- `API Key`
- `Model`

### 嵌入模型

- `Embedding API URL`
- `Embedding API Key`
- `Embedding Model`
- `Embedding Fields`

### 重排序模型

- `Rerank Enabled`
- `Rerank API URL`
- `Rerank API Key`
- `Rerank Model`

### 界面设置

- 浅色 / 暗色主题
- 背景图
- 背景遮罩
- UI 透明度

## 存档机制

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

立绘默认按槽位读取：

- `/static/sprites/slot_1`
- `/static/sprites/slot_2`
- `/static/sprites/slot_3`

## 开发入口

- 后端主入口：`app.py`
- 桌面启动器入口：`launcher.py`
- 页面模板：`templates/`
- 样式文件：`static/styles.css`


