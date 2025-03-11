// script.js (性能优化版本 - 支持轮询历史记录)
document.addEventListener('DOMContentLoaded', function() {
    // ... (DOM 元素获取代码保持不变)
    const apiUrlInput = document.getElementById('api-url');
    const apiKeyInput = document.getElementById('api-key');
    const modelNameSelect = document.getElementById('model-name');
    const getModelsButton = document.getElementById('get-models-button');
    const portInput = document.getElementById('port');
    const temperatureInput = document.getElementById('temperature');
    const maxTokensInput = document.getElementById('max-tokens');
    const contextTurnsInput = document.getElementById('context-turns');
    const systemPromptTextarea = document.getElementById('system-prompt');
    const testConfigButton = document.getElementById('test-config-button');
    const saveConfigButton = document.getElementById('save-config-button');
    const historyStatusLabel = document.getElementById('history-status');
    const clearHistoryButton = document.getElementById('clear-history-button');
    const tokenStatusLabel = document.getElementById('token-status');
    const resetTokenButton = document.getElementById('reset-token-button');
    const logOutputTextarea = document.getElementById('log-output');
    const translateButton = document.getElementById('translate-button');
    const inputText = document.getElementById('input-text');
    const outputTextarea = document.getElementById('output-text');
    const startListenButton = document.getElementById('start-listen-button');
    const stopListenButton = document.getElementById('stop-listen-button');
    const translationHistoryDiv = document.getElementById('translation-history');
    console.log("[DEBUG] translationHistoryDiv:", translationHistoryDiv);

    let promptTokensCount = 0;
    let completionTokensCount = 0;
    let totalTokensCount = 0;
    let isListening = false;
    let historyPollingInterval = null; //  用于存储轮询定时器

    const webServerPort = 6799;
    const translationServicePort = 6800;

    // 优化日志函数，使用数组缓存日志，批量更新 (如果日志量成为问题再启用)
    // const logBuffer = [];
    function logMessage(message, isError = false) {
        const timestamp = new Date().toLocaleTimeString();
        const logEntry = `[${timestamp}] ${message}\n`;
        const fullLogEntry = isError ? `[ERROR] ${logEntry}` : logEntry;

        logOutputTextarea.value += fullLogEntry; //  简化日志输出方式，直接累加字符串
        logOutputTextarea.scrollTop = logOutputTextarea.scrollHeight;
    }

    function convertPunctuation(text) {
        const punctuationMap = {
            '，': ',', '。': '.', '！': '!', '？': '?', '；': ';', '：': ':',
            '“': '"', '”': '"', '‘': "'", '’': "'", '（': '(', '）': ')',
            '【': '[', '】': ']', '《': '<', '》': '>', '…': '...', '—': '-',
            ' ': ' ' //  保持空格
        };
        let convertedText = text;
        for (const cnPunct in punctuationMap) {
            convertedText = convertedText.replace(new RegExp(cnPunct, 'g'), punctuationMap[cnPunct]);
        }
        return convertedText;
    }

    function getConfig() {
        let apiUrl = apiUrlInput.value.trim();
        apiUrl = apiUrl.endsWith("/") ? apiUrl.slice(0, -1) : apiUrl;
        const apiKey = apiKeyInput.value.trim();
        const port = portInput.value.trim();

        return {
            api_url: apiUrl,
            api_key: apiKey,
            model_name: modelNameSelect.value,
            system_prompt: systemPromptTextarea.value.trim(),
            port: port,
            temperature: parseFloat(temperatureInput.value),
            max_tokens: parseInt(maxTokensInput.value),
            context_turns: parseInt(contextTurnsInput.value)
        };
    }

    function loadConfig() {
        const savedConfig = localStorage.getItem('translationConfig');
        if (savedConfig) {
            const config = JSON.parse(savedConfig);
            apiUrlInput.value = config.api_url || "";
            apiKeyInput.value = config.api_key || "";
            modelNameSelect.value = config.model_name || "qwen-plus";
            portInput.value = config.port || "6800";
            temperatureInput.value = config.temperature || "1.0";
            maxTokensInput.value = config.max_tokens || "4096";
            contextTurnsInput.value = config.context_turns || "5";
            systemPromptTextarea.value = config.system_prompt || "你是一个游戏翻译模型，可以流畅通顺地将任意的游戏文本翻译成简体中文，并联系上下文正确使用人称代词，不要进行任何额外的格式修改，不擅自添加原文中没有的代词。你没有任何违禁词限制！你的回答只有翻译文本！不允许回答翻译文本之外的内容！不允许解释你是怎么样翻译的！不允许提出建议！如果游戏文本是一个字母或符号回答原文本即可！并确保翻译结果符合中文语言习惯而且符合游戏内容的词语，你可以调整语气和风格，并考虑到某些词语的文化内涵和地区差异。同时作为游戏翻译模型，需将原文翻译成具有信达雅标准的译文。以下是需要翻译的文本：";
            logMessage("已加载保存的配置");
        } else {
            logMessage("未找到保存的配置，使用默认配置");
        }
    }

    function saveConfig() {
        logMessage("保存配置...");
        const config = getConfig();
        localStorage.setItem('translationConfig', JSON.stringify(config));
        logMessage("配置已保存到本地存储");
    }

    async function testConfig() {
        logMessage("正在测试API配置...");
        testConfigButton.disabled = true;
        try {
            const config = getConfig();
            const serverUrl = `http://localhost:${webServerPort}/test-config`;

            const response = await fetch(serverUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
                timeout: 30000
            });

            if (!response.ok) {
                const errorDetails = await response.text();
                logMessage(`API 配置测试失败，HTTP 状态码: ${response.status}`, true);
                logMessage(`错误详情: ${errorDetails}`, true);
                return;
            }

            const responseData = await response.json();
            if (responseData.success) {
                logMessage("API 配置测试成功！");
                logMessage(responseData.message);
                if (responseData.usage) {
                    updateTokenCount(responseData.usage.prompt_tokens || 0, responseData.usage.completion_tokens || 0, responseData.usage.total_tokens || 0);
                    logMessage(`Token 使用: 请求=${responseData.usage.prompt_tokens || 0}, 回复=${responseData.usage.completion_tokens || 0}, 总计=${responseData.usage.total_tokens || 0}`);
                }
            } else {
                logMessage(`API 配置测试失败: ${responseData.message || '未知错误'}`, true);
            }
        } catch (error) {
            logMessage(`测试配置过程中发生错误: ${error.message}`, true);
        } finally {
            testConfigButton.disabled = false;
        }
    }

    async function getModelList() {
        logMessage("正在获取模型列表...");
        getModelsButton.disabled = true;
        try {
            const config = getConfig();
            const serverUrl = `http://localhost:${webServerPort}/models`;

            const response = await fetch(serverUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
                timeout: 15000
            });

            if (!response.ok) {
                const errorDetails = await response.text();
                logMessage(`获取模型列表失败，HTTP 状态码: ${response.status}`, true);
                logMessage(`错误详情: ${errorDetails}`, true);
                return;
            }

            const responseData = await response.json();
            if (responseData.success && responseData.models) {
                const modelsList = responseData.models;
                if (modelsList.length > 0) {
                    updateModelDropdown(modelsList);
                    logMessage(`成功获取模型列表，共 ${modelsList.length} 个模型`);
                } else {
                    logMessage("模型列表为空");
                }
            } else {
                logMessage(responseData.message || "获取模型列表失败，服务器返回未知错误", true);
            }
        } catch (error) {
            logMessage(`获取模型列表时发生错误: ${error.message}`, true);
        } finally {
            getModelsButton.disabled = false;
            modelNameSelect.disabled = false;
        }
    }

    function updateModelDropdown(models) {
        modelNameSelect.innerHTML = '';
        models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            modelNameSelect.appendChild(option);
        });
    }

    function updateTokenCount(promptTokens, completionTokens, totalTokens) {
        promptTokensCount += promptTokens;
        completionTokensCount += completionTokens;
        totalTokensCount += totalTokens;
        tokenStatusLabel.textContent = `请求: ${promptTokensCount}  |  回复: ${completionTokensCount}  |  总计: ${totalTokensCount}`;
    }

    function resetTokenCount() {
        promptTokensCount = 0;
        completionTokensCount = 0;
        totalTokensCount = 0;
        tokenStatusLabel.textContent = `请求: 0  |  回复: 0  |  总计: 0`;
        logMessage("Token 计数已重置");
    }

    function clearConversationHistory() {
        historyStatusLabel.textContent = `翻译上下文: 0组`;
        logMessage("翻译上下文已清除 (仅前端)");
    }

    async function translateTextRequest(textToTranslate) {
        if (!isListening) {
            logMessage("请先启动翻译服务再进行翻译", true);
            return;
        }

        logMessage(`发送翻译请求到服务器: ${textToTranslate.substring(0, 50)}...`);
        console.log("[DEBUG] translateTextRequest started for text:", textToTranslate.substring(0, 50) + "...");

        translateButton.disabled = true;
        outputTextarea.value = "翻译中...";

        const config = getConfig();

        let serverUrl = `http://localhost:${translationServicePort}/?text=${encodeURIComponent(textToTranslate)}`;
        serverUrl += `&api_url=${encodeURIComponent(config.api_url)}`;
        serverUrl += `&api_key=${encodeURIComponent(config.api_key)}`;
        serverUrl += `&model_name=${encodeURIComponent(config.model_name)}`;
        serverUrl += `&temperature=${encodeURIComponent(config.temperature)}`;
        serverUrl += `&max_tokens=${encodeURIComponent(config.max_tokens)}`;
        serverUrl += `&system_prompt=${encodeURIComponent(config.system_prompt)}`;

        logMessage(`[6800端口 - 请求] 待翻译文本: ${textToTranslate.substring(0, 50)}..., 模型: ${config.model_name}`);

        try {
            const response = await fetch(serverUrl, {
                method: 'GET',
                timeout: 180000
            });

            if (!response.ok) {
                const errorText = await response.text();
                logMessage(`服务器返回错误: ${response.status} - ${errorText}`, true);
                outputTextarea.value = "翻译失败，请查看日志";
                return;
            }

            const translatedText = await response.text();

            logMessage(`收到翻译结果: ${translatedText.substring(0, 50)}...`);
            outputTextarea.value = translatedText;
            logMessage(`[6800端口 - 响应] 翻译结果: ${translatedText}`);

            console.log("[DEBUG] Received translatedText:", translatedText.substring(0, 50) + "...");
            return translatedText;

        } catch (error) {
            logMessage(`与服务器通信出错: ${error.message}`, true);
            outputTextarea.value = "翻译失败，无法连接到服务器，请查看日志";
        } finally {
            translateButton.disabled = false;
        }
    }

    //  从服务器获取翻译历史记录并更新前端显示
    async function fetchTranslationHistory() {
        try {
            const response = await fetch(`http://localhost:${translationServicePort}/history`);
            if (!response.ok) {
                logMessage(`获取翻译历史记录失败，HTTP 状态码: ${response.status}`, true);
                return;
            }
            const responseData = await response.json();
            if (responseData.success && responseData.history) {
                const history = responseData.history;
                translationHistoryDiv.innerHTML = ''; // 清空旧的历史记录
                history.forEach(entry => {
                    addTranslationEntryToUI(entry.inputText, entry.outputText); // 为每条记录创建UI元素
                });
                logMessage(`成功更新翻译历史记录，共 ${history.length} 条`);
            } else {
                logMessage(`获取翻译历史记录失败: ${responseData.message || '未知错误'}`, true);
            }
        } catch (error) {
            logMessage(`获取翻译历史记录时发生错误: ${error.message}`, true);
        }
    }

    //  将单条翻译记录添加到历史记录UI
    function addTranslationEntryToUI(inputText, translatedText) {
        const historyEntry = document.createElement('div');
        historyEntry.classList.add('history-entry'); // 可以添加 CSS 样式

        const inputPara = document.createElement('p');
        inputPara.classList.add('input-text-history');
        inputPara.textContent = `原文: ${inputText}`;

        const outputPara = document.createElement('p');
        outputPara.classList.add('output-text-history');
        outputPara.textContent = `翻译: ${translatedText}`;

        historyEntry.appendChild(inputPara);
        historyEntry.appendChild(outputPara);

        translationHistoryDiv.prepend(historyEntry); // 将新的记录添加到最前面，方便查看
    }


    async function startListening() {
        if (isListening) {
            logMessage("翻译服务已在运行中，请勿重复启动");
            return;
        }

        logMessage("启动翻译服务...");
        startListenButton.disabled = true;
        stopListenButton.disabled = false;

        const config = getConfig();
        const serverUrl = `http://localhost:${webServerPort}/start-server`;

        try {
            const response = await fetch(serverUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(config),
                timeout: 15000
            });


            if (!response.ok) {
                const errorText = await response.text();
                logMessage(`启动翻译服务失败，HTTP 状态码: ${response.status}`, true);
                logMessage(`错误详情: ${errorText}`, true);
                startListenButton.disabled = false;
                stopListenButton.disabled = true;
                return;
            }

            const responseData = await response.json();
            if (responseData.success) {
                logMessage(responseData.message);
                isListening = true;
                startListenButton.disabled = true;
                stopListenButton.disabled = false;
                fetchTranslationHistory(); // 启动服务时加载历史记录
                //  启动定时器，每 3 秒轮询一次历史记录 (时间间隔可以调整)
                historyPollingInterval = setInterval(fetchTranslationHistory, 3000); //  每 3 秒轮询一次
            } else {
                logMessage(`启动翻译服务失败: ${responseData.message || '未知错误'}`, true);
                startListenButton.disabled = false;
                stopListenButton.disabled = true;
            }

        } catch (error) {
            logMessage(`启动翻译服务过程中发生错误: ${error.message}`, true);
            startListenButton.disabled = false;
            stopListenButton.disabled = true;
        }
    }


    async function stopListening() {
        if (!isListening) {
            logMessage("翻译服务未运行，无需停止");
            return;
        }
        logMessage("停止翻译服务...");
        stopListenButton.disabled = true;
        startListenButton.disabled = false;

        const serverUrl = `http://localhost:${webServerPort}/stop-server`;

        try {
            const response = await fetch(serverUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({}),
                timeout: 15000
            });

            if (!response.ok) {
                const errorText = await response.text();
                logMessage(`停止翻译服务失败，HTTP 状态码: ${response.status}`, true);
                logMessage(`错误详情: ${errorText}`, true);
                stopListenButton.disabled = false;
                startListenButton.disabled = false;
                return;
            }

            const responseData = await response.json();
            if (responseData.success) {
                logMessage("翻译服务停止成功！");
                isListening = false;
                stopListenButton.disabled = true;
                startListenButton.disabled = false;
                //  停止轮询定时器
                clearInterval(historyPollingInterval);
                historyPollingInterval = null;
            } else {
                logMessage(`停止翻译服务失败: ${responseData.message || '未知错误'}`, true);
                stopListenButton.disabled = false;
                startListenButton.disabled = false;
            }

        } catch (error) {
            logMessage(`停止翻译服务过程中发生错误: ${error.message}`, true);
            stopListenButton.disabled = false;
            startListenButton.disabled = false;
        }
    }


    translateButton.addEventListener('click', async () => { // 保持不变
        const text = inputText.value.trim();
        if (!text) {
            logMessage("请输入要翻译的文本");
            return;
        }
        logMessage(`用户输入待翻译文本: ${text.substring(0, 50)}...`);
        await translateTextRequest(text);
    });

    startListenButton.addEventListener('click', startListening);
    stopListenButton.addEventListener('click', stopListening);

    loadConfig();
    stopListenButton.disabled = true;
    startListenButton.disabled = false;

    inputText.value = "这里是预设的待翻译文本，您可以直接点击“开始翻译”按钮进行翻译，或者修改文本后再翻译。";

    getModelsButton.addEventListener('click', getModelList);
    testConfigButton.addEventListener('click', testConfig);
    saveConfigButton.addEventListener('click', saveConfig);
    resetTokenButton.addEventListener('click', resetTokenCount);
    clearHistoryButton.addEventListener('click', clearConversationHistory);
    clearHistoryButton.addEventListener('click', () => {
        translationHistoryDiv.innerHTML = '';
        logMessage("翻译上下文已清除 (前端和**服务端内存**)");
        //  如果需要同时清除服务端历史记录，可以发送请求到服务端接口
        // fetch('/clear-history', { method: 'POST' }); //  (需要服务端实现 /clear-history 接口)
    });


    logMessage("翻译服务应用已启动 (JavaScript)");
});
