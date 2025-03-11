# 这是基于原项目 [XUnity.LLMTranslate](https://github.com/HanFengRuYue/XUnity.LLMTranslate) 在Web端的性能改进版本。
## 该项目主要是为了方便在服务器上使用，因此去掉了原项目的GUI，改为Web端的API接口并使用HTML作为前端，node-js作为后端。实现了更快的前后处理速度并获得超低的延迟（实测使用gemini-2.0-flash进行翻译的速度在1s以内），较低的资源占用与更好的稳定性。

## 原项目链接：[XUnity大模型翻译v3](https://github.com/HanFengRuYue/XUnity.LLMTranslate)

这是一个基于大模型API的Unity游戏运行时文本自动翻译工具。该程序可以接收翻译客户端发送的HTTP请求，调用大模型API进行翻译，并返回翻译结果。

[//]: # (## 功能特点)

[//]: # (- 监听HTTP请求，解析需要翻译的文本)

[//]: # (- 调用大模型API进行翻译（支持多种大模型平台）)

[//]: # (- 自动将中文标点符号转换为英文标点符号)

[//]: # (- 美观的图形用户界面，支持高DPI显示)

[//]: # (- 自动获取平台支持的模型列表)

[//]: # (- 温度、最大Token数和上下文数量的统一控制面板)

[//]: # (- 支持配置保存和加载)

[//]: # (- 服务启动/停止控制)

[//]: # (- API配置测试功能)

[//]: # (- 实时运行日志)

[//]: # (- 翻译历史记录管理)

[//]: # (- Token使用统计)

[//]: # (## 安装)

[//]: # ()
[//]: # (1. 确保已安装Python 3.8或更高版本)

[//]: # (2. 安装所需依赖：)

[//]: # ()
[//]: # (```bash)

[//]: # (pip install -r requirements.txt)

[//]: # (```)

[//]: # ()
[//]: # (## 使用方法)

[//]: # ()
[//]: # (1. 运行程序：)

[//]: # ()
[//]: # (```bash)

[//]: # (python XUnity-LLMTranslateGUI.py)

[//]: # (```)

[//]: # ()
[//]: # (2. 在图形界面中配置：)

[//]: # (   - API URL：大模型API的地址)

[//]: # (   - API Key：访问API所需的密钥)

[//]: # (   - 模型名称：使用的大模型名称（可点击"获取模型列表"自动获取）)

[//]: # (   - 监听端口：服务监听的端口（默认6800）)

[//]: # (   - 温度：控制生成文本的随机性（0.0-2.0）)

[//]: # (   - 最大Token数量：限制API响应长度（默认4096）)

[//]: # (   - 翻译历史上下文数量：保留的历史对话组数（默认5）)

[//]: # (   - 系统提示：发送给大模型的系统角色指令)

[//]: # ()
[//]: # (3. 点击"保存配置"按钮保存配置)

[//]: # (4. 点击"测试配置"按钮测试API连接是否正常)

[//]: # (5. 点击"启动服务"按钮启动翻译服务)

[//]: # ()
[//]: # (## API使用)

[//]: # ()
[//]: # (翻译客户端可以通过以下方式发送翻译请求：)

[//]: # ()
[//]: # (```)

[//]: # (http://localhost:6800/?text=需要翻译的文本)

[//]: # (```)

[//]: # ()
[//]: # (服务器将返回翻译后的文本。)

[//]: # ()
[//]: # (## 支持的大模型平台)

[//]: # ()
[//]: # (本程序支持符合OpenAI Chat Completions API规范的大模型平台，包括但不限于：)

[//]: # ()
[//]: # (- 阿里云通义千问)

[//]: # (- 百度文心一言)

[//]: # (- 讯飞星火)

[//]: # (- OpenAI)

[//]: # (- Anthropic Claude)

[//]: # (- 其他支持兼容OpenAI接口的模型服务)

[//]: # ()
[//]: # (## 优化特性)

[//]: # ()
[//]: # (- 高效的线程池管理，确保资源正确释放)

[//]: # (- 优化的UI布局，界面简洁直观)

[//]: # (- 强大的错误处理机制)

[//]: # (- 可靠的服务关闭流程，防止程序卡死)

[//]: # (- Token使用统计和管理)

[//]: # (- 翻译历史记录控制)

[//]: # ()
[//]: # (## 注意事项)

[//]: # ()
[//]: # (- 请确保您有足够的API调用权限和配额)

[//]: # (- 根据您使用的大模型平台调整API URL和认证方式)

[//]: # (- 系统提示可以根据需要自定义，以获得更好的翻译效果)

[//]: # (- 如API无法正常调用，可尝试在地址后面加上/v1 )
