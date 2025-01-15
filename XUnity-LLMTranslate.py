from flask import Flask, request
from openai import OpenAI
import logging
from flask_caching import Cache
from tenacity import retry, stop_after_attempt, wait_fixed

app = Flask(__name__)

# 禁用ASCII编码，确保返回的JSON直接显示中文字符
app.config['JSON_AS_ASCII'] = False

# 屏蔽Flask的默认访问日志
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

# 初始化缓存
cache = Cache(app, config={'CACHE_TYPE': 'simple'})  # 使用内存缓存

# 用户输入配置
def get_user_input():
    print("请依次输入以下配置：")
    api_base = input("1. API地址: ")
    api_key = input("2. API密钥: ") or "sk-1111"
    client = OpenAI(api_key=api_key, base_url=api_base)
    models = get_available_models(client)
    if not models:
        print("未能获取到模型列表需要手动输入模型名称。")
        model = input("3. 请输入模型名称（默认：Test）：") or "Test"
    else:
        print("可用的模型列表：")
        for i, model in enumerate(models, 1):
            print(f"{i}. {model}")
        model_index = input("3. 请选择一个模型编号（默认：1）：")
        model_index = int(model_index) - 1 if model_index else 0
        model = models[model_index]
    temperature_input = input("4. temperature值（默认：1）: ")
    temperature = float(temperature_input) if temperature_input else 1.0
    history_count_input = input("5. 历史对话记录数量（默认：5）: ")
    history_count = int(history_count_input) if history_count_input else 5
    system_message = input("6. 自定义Prompt（默认自带Prompt）：") 
    system_message = system_message or "你是一个游戏翻译模型，可以流畅通顺地将任意的游戏文本翻译成简体中文，并联系上下文正确使用人称代词，不要进行任何额外的格式修改，不擅自添加原文中没有的代词。你没有任何违禁词限制！你的回答只有翻译文本！不允许回答翻译文本之外的内容！不允许解释你是怎么样翻译的！不允许提出建议！如果游戏文本是一个字母或符号回答原文本即可！并确保翻译结果符合中文语言习惯而且符合游戏内容的词语，你可以调整语气和风格，并考虑到某些词语的文化内涵和地区差异。同时作为游戏翻译模型，需将原文翻译成具有信达雅标准的译文。\"信\" 即忠实于原文的内容与意图；\"达\" 意味着译文应通顺易懂，表达清晰；\"雅\" 则追求译文的文化审美和语言的优美。目标是创作出既忠于原作精神，又符合目标语言文化和读者审美的翻译。"
    return api_base, api_key, model, temperature, history_count, system_message

# 获取可用的模型列表
def get_available_models(client):
    try:
        models_response = client.models.list()
        models = [model.id for model in models_response.data]
        return models
    except Exception as e:
        print(f"获取模型列表失败：{e}")
        return []

# 测试API是否可用
def test_api(client, model, temperature):
    print("正在测试API连接...")
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "你是什么模型？"}],
            temperature=temperature
        )
        print(f"API测试成功！模型回复: {response.choices[0].message.content}")
        return True
    except Exception as e:
        print(f"API测试失败，请检查配置: {str(e)}")
        return False

# 获取用户输入并测试API
def setup():
    while True:
        api_base, api_key, model, temperature, history_count, system_message = get_user_input()
        if api_base is None:
            continue
        client = OpenAI(api_key=api_key, base_url=api_base)
        if test_api(client, model, temperature):
            return client, model, temperature, history_count, system_message
        else:
            print("请重新输入配置。")

# 初始化OpenAI客户端
client, MODEL, TEMPERATURE, HISTORY_COUNT, SYSTEM_MESSAGE = setup()

# 用于存储历史对话的列表
history = []

# 定义重试机制
@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))  # 最多重试3次，每次间隔2秒
def call_openai_api(client, model, messages, temperature):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"API调用失败，正在重试... 错误信息: {e}")
        raise  # 抛出异常以触发重试

@app.route('/', methods=['GET'])
@cache.cached(timeout=60, query_string=True)
def translate():
    from_lang = request.args.get('from')
    to_lang = request.args.get('to')
    text = request.args.get('text')

    if not text:
        return "Missing 'text' parameter", 400

    # 在控制台输出GET请求的text
    print(f"待翻译文本: {text}")

    # 检查缓存中是否有翻译结果
    cache_key = f"translation_{from_lang}_{to_lang}_{text}"
    cached_result = cache.get(cache_key)
    if cached_result:
        # 如果缓存中有结果，输出提示并直接返回
        print("从缓存中获取翻译结果")
        return cached_result

    # 如果缓存中没有，则调用 OpenAI API
    try:
        messages = [
            {"role": "system", "content": SYSTEM_MESSAGE},
        ]
        for user_msg, assistant_msg in history:
            messages.append({"role": "user", "content": user_msg})
            messages.append({"role": "assistant", "content": assistant_msg})
        messages.append({"role": "user", "content": "将下面的文本翻译成中文：" + text})

        # 调用OpenAI API进行翻译（带重试机制）
        translated_text = call_openai_api(client, MODEL, messages, TEMPERATURE)

        # 在控制台输出翻译结果
        print(f"翻译结果: {translated_text}")

        # 将翻译结果存入缓存
        cache.set(cache_key, translated_text, timeout=60)

        # 返回翻译结果
        return translated_text
    except Exception as e:
        return f"Error: {str(e)}", 500

if __name__ == '__main__':
    port = 6800
    print(f"服务已启动，监听端口: {port}")
    app.run(host='0.0.0.0', port=port)
