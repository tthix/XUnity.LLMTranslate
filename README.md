# XUnity.LLMTranslate

[![Stars](https://img.shields.io/github/stars/HanFengRuYue/XUnity.LLMTranslate?style=social)](https://github.com/HanFengRuYue/XUnity.LLMTranslate/stargazers) 
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

通过大语言模型实现高效游戏文本翻译的Python解决方案，专为XUnity.AutoTranslator设计的多语言支持拓展。

## ✨ 主要特性

- 🚀 **即插即用** - 与XUnity.AutoTranslator无缝对接
- 🌍 **多语言适配** - 支持主流大模型（GPT/GLM/ERNIE等）
- 🔌 **REST API** - 标准化HTTP接口
- 🧠 **上下文记忆** - 智能处理对话场景文本
- ⚙️ **可视化配置** - 图形化参数调整界面
- 📊 **运行日志** - 实时监控翻译状态

## 📦 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 启动服务
```python
python XUnity-LLMTranslateGUI.py
```

## 🌐 使用方式
通过简单GET请求即可调用翻译服务：

**基础URL格式**：
```
http://localhost:6800/?text={需翻译文本}
```

### 跨语言调用示例

<details>
<summary><strong>👉 展开查看多语言调用示例</strong></summary>

#### Python
```python
import requests

text = "Attack the enemy!"
response = requests.get(f"http://localhost:6800/?text={requests.utils.quote(text)}")
print(response.text)  # 输出：攻击敌人！
```

#### C#
```csharp
using System.Net;

var text = WebUtility.UrlEncode("Game Over");
using var client = new WebClient();
var response = client.DownloadString($"http://localhost:6800/?text={text}");
Console.WriteLine(response);  // 输出：游戏结束
```

#### JavaScript
```javascript
const text = encodeURIComponent("Press Start Button");
fetch(`http://localhost:6800/?text=${text}`)
  .then(response => response.text())
  .then(console.log);  // 输出：按下开始按钮
```

#### Unity(C#)
```csharp
IEnumerator TranslateText(string originalText){
    string url = $"http://localhost:6800/?text={Uri.EscapeDataString(originalText)}";
    using UnityWebRequest request = UnityWebRequest.Get(url);
    yield return request.SendWebRequest();
    
    if(request.result == UnityWebRequest.Result.Success){
        string translated = request.downloadHandler.text;
        Debug.Log($"翻译结果: {translated}");
    }
}
```
</details>

## ⚙️ 配置指南
通过GUI界面可调整以下参数：

| 参数项           | 默认值           | 说明                                |
|------------------|------------------|------------------------------------|
| API地址          | OpenAI官方API     | 支持本地部署的大模型服务地址           |
| API密钥          | sk-xxx          | 大模型服务的认证密钥                  |
| 上下文记忆次数    | 5               | 保留的对话历史轮数（0为禁用）          |
| 温度参数         | 1.0             | 控制输出随机性（0-1值越大越随机）      |
| 系统提示         | 翻译专用预设     | 调整输出风格的指令模板                |

## 🔍 常用调试技巧

1. 校验服务是否运行：
```bash
curl "http://localhost:6800/?text=TEST"
```

2. 日志观察方法：
```
[运行日志]实时显示以下状态：
✅ 成功请求："收到请求: Hello"
🛑 错误记录："认证失败：无效的API密钥"
⚡ 性能监控："处理耗时：1.23s"
```

3. 特殊字符处理建议：
```python
# 处理日语需双重编码
text = urllib.parse.quote(urllib.parse.quote("こんにちは"))
```

## 📜 协议授权
本项目基于 MIT 协议开放使用，允许商业和非商业用途的二次开发。
```
