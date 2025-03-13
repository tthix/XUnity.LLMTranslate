// server.js (解决方案 2 - 支持翻译历史记录 + 本地缓存)
import open from 'open';
import express from 'express';
import cors from 'cors';
import fetch from 'node-fetch';
import * as dotenv from 'dotenv';
import fs from 'fs'; // 引入 fs 模块

dotenv.config();

const app = express();
const translateApp = express();

app.use(express.static('.'));
app.use(cors());
app.use(express.json());

translateApp.use(cors());
translateApp.use(express.json());

const webUIPort = process.env.WEB_UI_PORT || 6799;
const translationServicePort = process.env.PORT || 6800;
const TRANSLATION_RESULT_FILE = 'translationResult.json'; // 定义本地缓存文件路径

let isServerListening = false;
let currentConfig = {
    api_url: process.env.API_BASE_URL || "https://api.openai.com/v1",
    api_key: process.env.API_KEY,
    model_name: process.env.MODEL_NAME || "qwen-plus",
    system_prompt: process.env.SYSTEM_PROMPT || "你是一个游戏翻译模型...",
    temperature: 1.0,
    max_tokens: 4096,
};

// 新增：用于存储翻译历史记录 (内存存储，服务器重启会丢失)
const translationHistory = [];
// 创建一个存储翻译结果的map用于存储翻译结果
const translationResult = new Map();
const uncachedTranslations = new Map();

function logMessage(message) {
    const timestamp = new Date().toLocaleTimeString();
    console.log(`[${timestamp}] ${message}`);
}

// 保存 translationResult 到本地文件
function saveTranslationResult() {
    try {
        // 将 Map 转换为普通对象以便 JSON 序列化
        const obj = Object.fromEntries(translationResult.entries());
        fs.writeFileSync(TRANSLATION_RESULT_FILE, JSON.stringify(obj));
        logMessage(`翻译结果已保存到 ${TRANSLATION_RESULT_FILE}`);
    } catch (error) {
        logMessage(`保存翻译结果到文件失败: ${error.message}`);
        console.error("保存翻译结果错误:", error);
    }
}

// 从本地文件加载 translationResult
function loadTranslationResult() {
    try {
        if (fs.existsSync(TRANSLATION_RESULT_FILE)) {
            const data = fs.readFileSync(TRANSLATION_RESULT_FILE, 'utf-8');
            const obj = JSON.parse(data);
            // 将普通对象转换回 Map
            for (const [key, value] of Object.entries(obj)) {
                translationResult.set(key, value);
            }
            logMessage(`已加载翻译结果，共 ${translationResult.size} 条`);
        } else {
            logMessage("未找到翻译结果文件，将创建新文件");
        }
    } catch (error) {
        logMessage(`加载翻译结果文件失败: ${error.message}`);
        console.error("加载翻译结果错误:", error);
        // 如果加载失败，保持 translationResult 为空 Map
    }
}

// 处理翻译请求 (6800 端口)
async function handleTranslateRequest(req, res) {
    const textToTranslate = req.query.text;

    // if (!textToTranslate || textToTranslate.trim() === "") {
    //     return res.status(400).send("翻译失败: 输入文本为空");
    // }
    if (!textToTranslate || textToTranslate.trim().length < 2) {
        return res.status(400).json({ success: false, message: "翻译失败: 输入文本太短" });
    }
    if (!isServerListening) {
        return res.status(503).send("翻译失败: 翻译服务未启动");
    }
    if (!currentConfig.api_url || !currentConfig.api_key || !currentConfig.model_name) {
        return res.status(400).send("翻译失败: API配置不完整 (前端配置)");
    }

    // 新增：检查是否有缓存的翻译结果
    const cachedResult = translationResult.get(textToTranslate);
    if (cachedResult) {
        logMessage(`返回缓存的翻译结果: ${cachedResult.substring(0, 50)}...`);
        return res.send(cachedResult);
    }

    logMessage(`收到翻译请求: ${textToTranslate.substring(0, 50)}... 模型: ${currentConfig.model_name}`);


    let apiEndpoint = currentConfig.api_url;
    if (!apiEndpoint.endsWith("/chat/completions")) {
        apiEndpoint += "/chat/completions";
    }

    const headers = {
        'Authorization': `Bearer ${currentConfig.api_key}`,
        'Content-Type': 'application/json'
    };
    const messages = [
        { role: 'system', content: currentConfig.system_prompt },
        { role: 'user', content: textToTranslate }
    ];
    const data = {
        model: currentConfig.model_name,
        messages: messages,
        temperature: currentConfig.temperature,
        max_tokens: currentConfig.max_tokens
    };

    try {
        logMessage(`正在发送翻译请求到API... (Temperature: ${currentConfig.temperature}, Max Tokens: ${currentConfig.max_tokens})`);
        const response = await fetch(apiEndpoint, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(data),
            signal: AbortSignal.timeout(180000) // 使用 AbortSignal 实现超时控制，更现代的方式
        });

        if (!response.ok) {
            logMessage(`API 请求失败，状态码: ${response.status}`);
            const errorText = await response.text();
            logMessage(`API 错误详情: ${errorText}`);
            return res.status(response.status).send(`翻译失败: API 返回错误码 ${response.status}`);
        }

        const responseData = await response.json();

        if (!responseData.choices || responseData.choices.length === 0 || !responseData.choices[0].message || !responseData.choices[0].message.content) {
            logMessage(`API 返回无效的响应结构: ${JSON.stringify(responseData)}`);
            return res.status(500).send("翻译失败: API 返回无效的响应结构");
        }

        let translatedText = responseData.choices[0].message.content;

        if (!translatedText || translatedText.trim() === "") {
            logMessage("警告: API返回了空的翻译结果");
            return res.status(200).send("");
        }

        const thinkingRegex = /<(?:thinking|think)>(.*?)<\/(?:thinking|think)>/gs;
        const originalLength = translatedText.length;
        translatedText = translatedText.replace(thinkingRegex, '').trim();
        if (translatedText.length !== originalLength) {
            logMessage(`已移除思维链内容 (减少了 ${originalLength - translatedText.length} 字符)`);
        }

        const maxLength = 10000;
        if (translatedText.length > maxLength) {
            logMessage(`警告: 翻译结果过长，已截断至 ${maxLength} 字符`);
            translatedText = translatedText.substring(0, maxLength) + "...(内容过长已截断)";
        }

        logMessage(`翻译完成，返回结果: ${translatedText.substring(0, 50)}...`);

        // 新增：将翻译记录添加到历史记录
        const historyEntry = {
            inputText: textToTranslate,
            outputText: translatedText.trim()
        };
        translationHistory.unshift(historyEntry); // 添加到历史记录数组的开头

        // 新增：将翻译结果缓存起来
        translationResult.set(textToTranslate, translatedText.trim());
        uncachedTranslations.set(textToTranslate, translatedText.trim());

        res.send(translatedText.trim());

    } catch (error) {
        logMessage(`翻译请求出错: ${error.message}`);
        console.error("翻译请求详细错误:", error);
        if (error.name === 'AbortError') { // 捕获 AbortError
            return res.status(504).send("翻译失败: API请求超时");
        } else if (error.message.includes('ECONNREFUSED') || error.message.includes('ENOTFOUND')) {
            return res.status(502).send("翻译失败: 无法连接到API服务器，请检查网络或API URL是否正确");
        }
        res.status(500).send(`翻译失败: 服务器内部错误 ${error.message}`);
    }
}

translateApp.get('/', handleTranslateRequest);

// 新增接口：获取翻译历史记录
translateApp.get('/history', (req, res) => {
    // 返回完整的翻译历史记录
    res.json({ success: true, history: translationHistory });
});


// 启动翻译服务 (6799 端口) - 同时用于接收用户配置
app.post('/start-server', async (req, res) => {
    if (isServerListening) {
        return res.json({ success: false, message: "翻译服务已在运行中，请勿重复启动" });
    }

    currentConfig = { ...currentConfig, ...req.body };

    isServerListening = true;
    logMessage(`翻译服务已启动`);
    res.json({ success: true, message: `翻译服务已启动` });
});


async function handleTestConfigRequest(req, res) {
    const config = req.body;
    const apiUrl = config.api_url;
    const apiKey = config.api_key;
    const modelName = config.model_name;
    const temperature = parseFloat(config.temperature) || 1.0;
    const maxTokens = parseInt(config.max_tokens) || 4096;


    if (!apiUrl) {
        return res.status(400).json({ success: false, message: "错误: API URL不能为空" });
    }
    if (!apiKey) {
        return res.status(400).json({ success: false, message: "错误: API Key不能为空" });
    }
    if (!modelName) {
        return res.status(400).json({ success: false, message: "错误: 模型名称不能为空" });
    }

    let apiEndpoint = apiUrl;
    if (!apiEndpoint.endsWith("/chat/completions")) {
        apiEndpoint += "/chat/completions";
    }


    const headers = {
        'Authorization': `Bearer ${apiKey}`,
        'Content-Type': 'application/json'
    };
    const messages = [
        { role: 'system', content: 'You are a helpful assistant.' },
        { role: 'user', content: 'Hello, can you hear me? Please respond with a simple yes.' }
    ];
    const data = {
        model: modelName,
        messages: messages,
        temperature: temperature,
        max_tokens: maxTokens
    };

    logMessage(`API URL: ${apiUrl}`);
    logMessage(`Model: ${modelName}`);
    logMessage(`Temperature: ${temperature}`);
    logMessage(`Max Tokens: ${maxTokens}`);
    logMessage("正在发送测试请求...");

    try {
        const response = await fetch(apiEndpoint, {
            method: 'POST',
            headers: headers,
            body: JSON.stringify(data),
            signal: AbortSignal.timeout(30000) // 优化：使用 AbortSignal 实现超时控制
        });

        if (!response.ok) {
            logMessage(`API 请求失败 (测试配置)，状态码: ${response.status}`);
            const errorText = await response.text();
            logMessage(`API 错误详情: ${errorText}`);
            console.log("原始响应文本:", errorText);
            return res.status(response.status).json({ success: false, message: `API 请求失败，HTTP 状态码: ${response.status}`, error_details: errorText });
        }

        const responseData = await response.json();

        try {
            const replyContent = responseData.choices[0].message.content;
            const result = {
                success: true,
                message: `API响应成功！回复内容: ${replyContent}`,
                content: replyContent
            };

            if (responseData.usage) {
                const usage = responseData.usage;
                result.usage = usage;
                logMessage(`Token使用: 请求=${usage.prompt_tokens || 0}, 回复=${usage.completion_tokens || 0}, 总计=${usage.total_tokens || 0}`);
            }
            logMessage("配置测试成功！API响应正常。");
            return res.json(result);

        } catch (e) {
            logMessage(`解析API响应时出错: ${e}, 原始响应: ${JSON.stringify(responseData)}`);
            return res.status(500).json({ success: false, message: `解析API响应时出错: ${e}`, raw_response: responseData });
        }


    } catch (error) {
        logMessage(`测试配置出错: ${error.message}`);
        console.error("测试配置详细错误:", error);
        if (error.name === 'AbortError') { // 捕获 AbortError
            return res.status(504).json({ success: false, message: "错误: API请求超时" });
        } else if (error.message.includes('ECONNREFUSED') || error.message.includes('ENOTFOUND')) {
            return res.status(502).json({ success: false, message: "错误: 无法连接到API服务器，请检查网络或API URL是否正确" });
        }
        return res.status(500).json({ success: false, message: `测试配置时发生错误: ${error.message}` });
    }
}

app.post('/test-config', handleTestConfigRequest);


async function handleGetModelsRequest(req, res) {
    const config = req.body;
    let apiUrl = config.api_url;
    const apiKey = config.api_key;
    if (!apiUrl) {
        return res.status(400).json({ success: false, message: "获取模型列表失败: API URL不能为空" });
    }
    if (!apiKey) {
        return res.status(400).json({ success: false, message: "获取模型列表失败: API Key不能为空" });
    }

    if (!apiUrl.endsWith("/chat/completions")) {
        apiUrl = apiUrl.replace(/\/$/, "") + "/chat/completions";
    }

    const baseURL = apiUrl.replace(/\/chat\/completions$/, "");
    const endpoints = [
        `${baseURL}/models`,
        `${baseURL}/v1/models`,
        apiUrl.replace('/chat/completions', '/models')
    ];

    const headers = {
        'Authorization': `Bearer ${apiKey}`,
        'Accept': 'application/json'
    };
    let modelsList = [];
    let success = false;
    let errorDetails = null;


    for (const endpoint of endpoints) {
        logMessage(`正在尝试模型列表 API 端点: ${endpoint}`);
        try {
            const response = await fetch(endpoint, {
                headers: headers,
                signal: AbortSignal.timeout(15000) // 优化：使用 AbortSignal 实现超时控制
            });

            if (response.status !== 200) {
                errorDetails = { status: response.status, text: await response.text() };
                logMessage(`请求失败，状态码: ${response.status}`);
                continue;
            }

            const responseData = await response.json();

            if (responseData.data && Array.isArray(responseData.data)) {
                modelsList = responseData.data.map(model => model.id || '未知模型');
                success = true;
                break;
            } else if (responseData.models && Array.isArray(responseData.models)) {
                modelsList = responseData.models.map(model => model.id || model.name || '未知模型');
                success = true;
                break;
            } else if (responseData.model_list && Array.isArray(responseData.model_list)) {
                modelsList = responseData.model_list.map(model => model.model_name || model.name || '未知模型');
                success = true;
                break;
            }
            else {
                logMessage(`无法识别的API响应格式，原始响应: ${JSON.stringify(responseData)}`);
                errorDetails = { message: "无法识别的API响应格式", rawResponse: responseData };
            }


        } catch (error) {
            logMessage(`请求模型列表出错: ${error.message}`);
            console.error("获取模型列表详细错误:", error);
            errorDetails = { message: error.message };
            continue;
        }
    }

    if (success) {
        logMessage(`成功获取模型列表，共 ${modelsList.length} 个模型`);
        return res.json({ success: true, models: modelsList, message: `成功获取模型列表，共 ${modelsList.length} 个模型` });
    } else {
        logMessage("无法获取模型列表，所有已知API端点尝试均失败");
        let errorMessage = "无法获取模型列表，请检查API配置和URL";
        if (errorDetails) {
            if (errorDetails.status) {
                errorMessage += `, HTTP 状态码: ${errorDetails.status}`;
            }
            if (errorDetails.text) {
                errorMessage += `, 错误详情: ${errorDetails.text.substring(0, 200)}...`;
                console.log("模型列表原始错误响应文本:", errorDetails.text);
            }
            if (errorDetails.message) {
                errorMessage += `, 错误信息: ${errorDetails.message}`;
            }
        }
        return res.status(500).json({ success: false, message: errorMessage, error_details: errorDetails });
    }
}

app.post('/models', handleGetModelsRequest);

app.post('/stop-server', async (req, res) => {
    if (!isServerListening) {
        return res.json({ success: false, message: "翻译服务未在运行，无法停止" });
    }
    isServerListening = false;
    logMessage("翻译服务已停止");
    res.json({ success: true, message: "翻译服务已停止" });
});

app.get('/health', (req, res) => {
    res.send({ status: 'OK', message: 'Web Server is running' });
});
app.get('/', (req, res) => {
    res.sendFile('index.html', { root: '.' });
});

// 在启动翻译服务之前加载本地缓存
loadTranslationResult();

const serverInstance = app.listen(webUIPort, () => {
    logMessage(`Web服务器已启动，监听端口 ${webUIPort}`);
    const serverUrl = `http://localhost:${webUIPort}`;
    open(serverUrl).then(() => {
        logMessage(`网页已在浏览器中打开: ${serverUrl}`);
    }).catch(error => {
        logMessage(`打开网页失败: ${error.message}`);
    });
});

const translateServerInstance = translateApp.listen(translationServicePort, () => {
    logMessage(`翻译服务已启动，监听端口 ${translationServicePort}`);
});

// 设置每 10 秒保存一次积累的翻译结果到 translationResult
setInterval(() => {
    if (uncachedTranslations.size > 0) {
        saveTranslationResult();
        uncachedTranslations.clear();
    }
}, 10000);

logMessage(`Web服务器和翻译服务初始化完成，等待手动启动翻译服务监听器...`);
