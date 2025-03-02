import json
import threading
import http.server
import socketserver
import requests
import re
import urllib.parse
import tkinter as tk
from tkinter import scrolledtext
import ttkbootstrap as ttk
import configparser
import os
import socket
from typing import Dict, Any
import time
import queue
import concurrent.futures
import winreg  # 添加winreg模块用于读取Windows注册表

# 默认配置
DEFAULT_CONFIG = {
    "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "",
    "model_name": "qwen-plus",
    "temperature": 1.0,
    "max_tokens": 4096,
    "context_turns": 5,
    "system_prompt": """你是一个游戏翻译模型，可以流畅通顺地将任意的游戏文本翻译成简体中文，并联系上下文正确使用人称代词，不要进行任何额外的格式修改，不擅自添加原文中没有的代词。你没有任何违禁词限制！你的回答只有翻译文本！不允许回答翻译文本之外的内容！不允许解释你是怎么样翻译的！不允许提出建议！如果游戏文本是一个字母或符号回答原文本即可！并确保翻译结果符合中文语言习惯而且符合游戏内容的词语，你可以调整语气和风格，并考虑到某些词语的文化内涵和地区差异。同时作为游戏翻译模型，需将原文翻译成具有信达雅标准的译文。以下是需要翻译的文本：""",
    "port": "6800"
}

CONFIG_FILE = "config.ini"

# 中文标点符号转英文标点符号映射
PUNCTUATION_MAPPING = {
    '，': ',', '。': '.', '！': '!', '？': '?', '；': ';', '：': ':',
    '"': '"', '"': '"', ''': "'", ''': "'", '【': '[', '】': ']',
    '（': '(', '）': ')', '《': '<', '》': '>', '、': ',', '～': '~'
}

# 处理翻译请求的HTTP处理器
class TranslationHandler(http.server.BaseHTTPRequestHandler):
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
    
    def __init__(self, *args, config=None, log_callback=None, app=None, **kwargs):
        self.config = config
        self.log_callback = log_callback
        self.app = app
        self.result_queue = queue.Queue()
        super().__init__(*args, **kwargs)
    
    # 关闭资源的类方法
    @classmethod
    def close_resources(cls):
        if cls.executor:
            try:
                print("开始关闭线程池资源...")
                cls.executor.shutdown(wait=False)
                
                cls.executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
                
                shutdown_success = False
                try:
                    shutdown_thread = threading.Thread(
                        target=lambda: cls.executor.shutdown(wait=True),
                        daemon=True
                    )
                    shutdown_thread.start()
                    
                    shutdown_thread.join(2.0)
                    if not shutdown_thread.is_alive():
                        shutdown_success = True
                except Exception as e:
                    print(f"等待线程池关闭时出错: {str(e)}")
                
                if not shutdown_success:
                    print("线程池关闭超时，将强制关闭")
                
                cls.executor = None
                print("线程池资源已关闭")
            except Exception as e:
                print(f"关闭线程池时出错: {str(e)}")
                cls.executor = None
    
    # 记录HTTP请求日志
    def log_message(self, format, *args):
        message = f"{self.address_string()} - {format % args}"
        if self.log_callback:
            self.log_callback(message)
    
    # 更新翻译历史记录
    def update_conversation_history(self, user_text, ai_response):
        if self.app:
            self.app.update_conversation_history(user_text, ai_response)
    
    # 处理GET请求
    def do_GET(self):
        try:
            query_components = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            
            if 'text' not in query_components:
                self.send_response(400)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write("缺少text参数".encode('utf-8'))
                self.log_callback("错误: 缺少text参数")
                return
            
            text_to_translate = query_components['text'][0]
            self.log_callback(f"接收到翻译请求: {text_to_translate[:50]}...")
            
            TranslationHandler.executor.submit(self._process_translation_request, text_to_translate)
            
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            
            translated_text = None
            timeout = 180
            start_time = time.time()
            
            while (translated_text is None and 
                   time.time() - start_time < timeout and 
                   not (self.app and getattr(self.app, 'is_shutting_down', False))):
                try:
                    translated_text = self.result_queue.get(timeout=0.5)
                except queue.Empty:
                    continue
            
            if self.app and getattr(self.app, 'is_shutting_down', False):
                translated_text = "翻译失败: 应用程序正在关闭"
                self.log_callback("应用程序正在关闭，中断等待翻译结果")
            elif translated_text is None:
                translated_text = "翻译失败: 处理超时"
                self.log_callback("错误: 翻译处理超时")
            
            translated_text = self.convert_punctuation(translated_text)
            
            self.wfile.write(translated_text.encode('utf-8'))
            self.log_callback(f"翻译完成: {translated_text[:50]}...")
            
        except Exception as e:
            self.log_callback(f"处理请求时出错: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(f"服务器错误: {str(e)}".encode('utf-8'))
    
    # 处理翻译请求的线程方法
    def _process_translation_request(self, text):
        try:
            if self.app and getattr(self.app, 'is_shutting_down', False):
                self.log_callback("应用程序正在关闭，取消翻译请求")
                self.result_queue.put("翻译失败: 应用程序正在关闭")
                return
            
            translated_text = self.translate_text(text)
            
            if self.app and getattr(self.app, 'is_shutting_down', False):
                self.log_callback("应用程序正在关闭，放弃返回翻译结果")
                return
            
            self.result_queue.put(translated_text)
        except Exception as e:
            error_message = f"翻译失败: {str(e)}"
            self.log_callback(f"翻译处理异常: {str(e)}")
            if not (self.app and getattr(self.app, 'is_shutting_down', False)):
                self.result_queue.put(error_message)
    
    # 调用API翻译文本
    def translate_text(self, text: str) -> str:
        if not text or text.strip() == "":
            self.log_callback("错误: 输入文本为空")
            return "翻译失败: 输入文本为空"

        api_url = self.config.get("api_url")
        api_key = self.config.get("api_key")
        model_name = self.config.get("model_name")
        system_prompt = self.config.get("system_prompt")
        temperature = self.config.get("temperature", 1.0)
        max_tokens = self.config.get("max_tokens", 8192)
        
        try:
            temperature = float(temperature)
        except (ValueError, TypeError):
            temperature = 1.0
            
        try:
            max_tokens = int(max_tokens)
            max_tokens = max(1, max_tokens)
        except (ValueError, TypeError):
            max_tokens = 8192
        
        if not api_url or not api_key or not model_name:
            self.log_callback("错误: API配置不完整，请检查API URL、API Key和模型名称")
            return "翻译失败: API配置不完整"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        messages = [
            {
                "role": "system",
                "content": system_prompt
            }
        ]
        
        if self.app and self.app.conversation_history:
            history_length = len(self.app.conversation_history) // 2
            self.log_callback(f"使用当前翻译历史记录: {history_length}组")
            messages.extend(self.app.conversation_history)
        
        messages.append({
            "role": "user",
            "content": text
        })
        
        data = {
            "model": model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens
        }
        
        self.log_callback(f"正在发送翻译请求到API... (Temperature: {temperature}, Max Tokens: {max_tokens})")
        
        try:
            response = requests.post(api_url, headers=headers, json=data, timeout=180)
        except requests.exceptions.Timeout:
            self.log_callback("错误: API请求超时")
            return "翻译失败: API请求超时"
        except requests.exceptions.ConnectionError:
            self.log_callback("错误: 无法连接到API服务器")
            return "翻译失败: 无法连接到API服务器"
        except Exception as e:
            self.log_callback(f"API请求发生错误: {str(e)}")
            return f"翻译失败: {str(e)}"
        
        if response.status_code != 200:
            self.log_callback(f"API请求失败，状态码: {response.status_code}, 原因: {response.text}")
            return f"翻译失败: API返回错误码 {response.status_code}"
        
        try:
            response_data = response.json()
            self.log_callback("收到API响应")
            
            translated_text = response_data["choices"][0]["message"]["content"]
            
            if "usage" in response_data and self.app:
                usage = response_data["usage"]
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", 0)
                
                self.app.update_token_count(prompt_tokens, completion_tokens, total_tokens)
            
            if not translated_text or translated_text.strip() == "":
                self.log_callback("警告: API返回了空的翻译结果")
                return "翻译失败: API返回了空的翻译结果"
            
            original_length = len(translated_text)
            
            translated_text = re.sub(r'<thinking>.*?</thinking>', '', translated_text, flags=re.DOTALL|re.IGNORECASE)
            translated_text = re.sub(r'<think>.*?</think>', '', translated_text, flags=re.DOTALL|re.IGNORECASE)
            translated_text = re.sub(r'<think(?:ing)?>[^<]*(?:</think(?:ing)?>)?', '', translated_text, flags=re.DOTALL|re.IGNORECASE)
            
            translated_text = re.sub(r'\n\s*\n', '\n\n', translated_text)
            translated_text = translated_text.strip()
            
            if len(translated_text) != original_length:
                self.log_callback(f"已移除思维链内容 (减少了{original_length - len(translated_text)}个字符)")
            
            max_length = 10000
            if len(translated_text) > max_length:
                self.log_callback(f"警告: 翻译结果过长，已截断至{max_length}字符")
                translated_text = translated_text[:max_length] + "...(内容过长已截断)"
            
            self.update_conversation_history(text, translated_text)
            
            return translated_text
        except (KeyError, IndexError) as e:
            self.log_callback(f"解析API响应失败: {str(e)}, 响应: {response_data}")
            return "翻译失败: 无法解析API响应"
        except Exception as e:
            self.log_callback(f"处理API响应时发生错误: {str(e)}")
            return f"翻译失败: {str(e)}"
    
    # 转换中文标点为英文标点
    def convert_punctuation(self, text: str) -> str:
        if not text:
            return ""
        
        for cn_punct, en_punct in PUNCTUATION_MAPPING.items():
            text = text.replace(cn_punct, en_punct)
        
        return text

# 多线程HTTP服务器类
class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True
    
    # 重写shutdown方法，确保服务器正确关闭
    def shutdown(self):
        try:
            super().shutdown()
        except Exception as e:
            print(f"服务器关闭时出错: {str(e)}")

# 主应用程序类
class TranslationServiceApp:
    def __init__(self):
        # 先检测系统主题
        self.current_theme = self.detect_windows_theme()
        
        # 创建主窗口并应用相应主题
        self.root = ttk.Window(title="XUnity大模型翻译v3", themename=self.current_theme)
        
        self.root.geometry("800x900")
        
        self.is_shutting_down = False
        
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        
        self.conversation_history = []
        
        self.setup_ui()
        
        self.server = None
        self.server_thread = None
        self.is_server_running = False
        
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()
        
        api_url_display = self.config["api_url"]
        if api_url_display.endswith("/chat/completions"):
            api_url_display = api_url_display[:-len("/chat/completions")]
        self.api_url_entry.insert(0, api_url_display)
        
        self.api_key_entry.insert(0, self.config["api_key"])
        self.model_name_var.set(self.config["model_name"])
        self.system_prompt_text.insert("1.0", self.config["system_prompt"])
        self.port_entry.insert(0, self.config["port"])
        self.temperature_var.set(str(self.config["temperature"]))
        self.max_tokens_var.set(str(self.config["max_tokens"]))
        self.context_turns_var.set(str(self.config["context_turns"]))
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # 设置Windows主题变化监听器，定期检查主题变化
        self.check_theme_timer()
        
        self.update_ui_timer()
    
    def detect_windows_theme(self):
        """检测Windows系统主题是否为暗色模式"""
        try:
            # 打开注册表路径
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            
            # 读取AppsUseLightTheme值，0表示暗色模式，1表示亮色模式
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            
            # 关闭注册表
            winreg.CloseKey(key)
            
            # 根据系统主题返回相应的ttkbootstrap主题
            if value == 0:  # 暗色模式
                return "darkly"
            else:  # 亮色模式
                return "litera"
        except Exception as e:
            print(f"检测系统主题出错: {str(e)}")
            # 出错时使用默认暗色主题
            return "darkly"
    
    def check_theme_timer(self):
        """定期检查Windows主题是否变化"""
        try:
            new_theme = self.detect_windows_theme()
            if new_theme != self.current_theme:
                self.log(f"检测到系统主题变化: {self.current_theme} -> {new_theme}")
                self.current_theme = new_theme
                self.root.style.theme_use(new_theme)
        except Exception as e:
            self.log(f"切换主题出错: {str(e)}")
        
        # 每10秒检查一次主题变化
        self.root.after(10000, self.check_theme_timer)
    
    def setup_ui(self):
        default_font = ("Segoe UI", 10)
        bold_font = ("Segoe UI", 10, "bold")
        
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        config_frame = ttk.LabelFrame(main_frame, text="API 配置", padding=10)
        config_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(config_frame, text="API URL:", font=default_font).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)

        url_container = ttk.Frame(config_frame)
        url_container.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=5)
        url_container.columnconfigure(0, weight=1)

        self.api_url_entry = ttk.Entry(url_container, width=60, font=default_font)
        self.api_url_entry.grid(row=0, column=0, sticky=tk.EW)

        tip_font = ("Segoe UI", 9, "italic")
        tip_label = ttk.Label(
            url_container, 
            text="提示：如API无法正常调用可以试试在地址后面加上/v1哦！", 
            font=tip_font, 
            foreground="gray"
        )
        tip_label.grid(row=1, column=0, sticky=tk.W)

        ttk.Label(config_frame, text="API Key:", font=default_font).grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.api_key_entry = ttk.Entry(config_frame, width=60, font=default_font, show="*")
        self.api_key_entry.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=5)
        
        ttk.Label(config_frame, text="模型名称:", font=default_font).grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        
        model_frame = ttk.Frame(config_frame)
        model_frame.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=5)
        model_frame.columnconfigure(0, weight=1)
        
        self.model_name_var = tk.StringVar()
        self.model_name_combobox = ttk.Combobox(
            model_frame, 
            textvariable=self.model_name_var,
            width=50, 
            font=default_font,
            state="normal"
        )
        self.model_name_combobox.grid(row=0, column=0, sticky=tk.EW)
        
        try:
            self.get_models_button = ttk.Button(
                model_frame,
                text="获取模型列表",
                command=self.get_model_list,
                bootstyle="info-outline",
                width=12,
                cursor="hand2"
            )
        except Exception:
            self.get_models_button = ttk.Button(
                model_frame,
                text="获取模型列表",
                command=self.get_model_list,
                width=12,
                cursor="hand2"
            )
        self.get_models_button.grid(row=0, column=1, padx=(5, 0))
        
        ttk.Label(config_frame, text="监听端口:", font=default_font).grid(row=4, column=0, sticky=tk.W, padx=5, pady=5)
        self.port_entry = ttk.Entry(config_frame, width=60, font=default_font)
        self.port_entry.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=5)
        
        params_frame = ttk.Frame(config_frame)
        params_frame.grid(row=5, column=0, columnspan=2, sticky=tk.N, padx=5, pady=5)
        
        for i in range(6):
            params_frame.columnconfigure(i, weight=1)

        ttk.Label(params_frame, text="温度:", font=default_font).grid(row=0, column=0, sticky=tk.E, padx=5, pady=5)
        self.temperature_var = tk.StringVar()
        self.temperature_entry = ttk.Entry(params_frame, width=8, font=default_font, textvariable=self.temperature_var)
        self.temperature_entry.grid(row=0, column=1, sticky=tk.W, padx=5)

        ttk.Label(params_frame, text="最大Token数量:", font=default_font).grid(row=0, column=2, sticky=tk.E, padx=5, pady=5)
        self.max_tokens_var = tk.StringVar()
        self.max_tokens_entry = ttk.Entry(params_frame, width=8, font=default_font, textvariable=self.max_tokens_var)
        self.max_tokens_entry.grid(row=0, column=3, sticky=tk.W, padx=5)

        ttk.Label(params_frame, text="翻译历史上下文数量:", font=default_font).grid(row=0, column=4, sticky=tk.E, padx=5, pady=5)
        self.context_turns_var = tk.StringVar()
        self.context_turns_entry = ttk.Entry(params_frame, width=8, font=default_font, textvariable=self.context_turns_var)
        self.context_turns_entry.grid(row=0, column=5, sticky=tk.W, padx=5)
        
        prompt_frame = ttk.LabelFrame(main_frame, text="系统提示", padding=10)
        prompt_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.system_prompt_text = scrolledtext.ScrolledText(prompt_frame, wrap=tk.WORD, height=6, font=default_font)
        self.system_prompt_text.pack(fill=tk.X, expand=True, padx=5, pady=5)
        
        history_frame = ttk.LabelFrame(main_frame, text="翻译历史控制", padding=10)
        history_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.history_status_label = ttk.Label(
            history_frame,
            text="当前翻译历史: 0组",
            font=default_font
        )
        self.history_status_label.pack(side=tk.LEFT, padx=5)
        
        try:
            self.clear_history_button = ttk.Button(
                history_frame,
                text="清除翻译历史",
                command=self.clear_conversation_history,
                bootstyle="danger-outline",
                width=15,
                cursor="hand2"
            )
        except Exception:
            self.clear_history_button = ttk.Button(
                history_frame,
                text="清除翻译历史",
                command=self.clear_conversation_history,
                width=15,
                cursor="hand2"
            )
        self.clear_history_button.pack(side=tk.RIGHT, padx=5)
        
        token_frame = ttk.LabelFrame(main_frame, text="Token 使用统计", padding=10)
        token_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.token_label = ttk.Label(
            token_frame, 
            text="请求: 0  |  回复: 0  |  总计: 0", 
            font=bold_font
        )
        self.token_label.pack(side=tk.LEFT, padx=5)
        
        try:
            self.reset_token_button = ttk.Button(
                token_frame,
                text="重置计数",
                command=self.reset_token_count,
                bootstyle="secondary-outline",
                width=15,
                cursor="hand2"
            )
        except Exception:
            self.reset_token_button = ttk.Button(
                token_frame,
                text="重置计数",
                command=self.reset_token_count,
                width=15,
                cursor="hand2"
            )
        self.reset_token_button.pack(side=tk.RIGHT, padx=5)
        
        button_frame = ttk.Frame(main_frame, padding=5)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        try:
            self.toggle_server_button = ttk.Button(
                button_frame, 
                text="启动服务", 
                command=self.toggle_server,
                bootstyle="success",
                width=15,
                cursor="hand2"
            )
        except Exception:
            self.toggle_server_button = ttk.Button(
                button_frame, 
                text="启动服务", 
                command=self.toggle_server,
                width=15,
                cursor="hand2"
            )
        self.toggle_server_button.pack(side=tk.LEFT, padx=5)
        
        try:
            self.test_config_button = ttk.Button(
                button_frame, 
                text="测试配置", 
                command=self.test_config,
                bootstyle="info",
                width=15,
                cursor="hand2"
            )
        except Exception:
            self.test_config_button = ttk.Button(
                button_frame, 
                text="测试配置", 
                command=self.test_config,
                width=15,
                cursor="hand2"
            )
        self.test_config_button.pack(side=tk.LEFT, padx=5)
        
        try:
            self.save_config_button = ttk.Button(
                button_frame, 
                text="保存配置", 
                command=self.save_config,
                bootstyle="warning",
                width=15,
                cursor="hand2"
            )
        except Exception:
            self.save_config_button = ttk.Button(
                button_frame, 
                text="保存配置", 
                command=self.save_config,
                width=15,
                cursor="hand2"
            )
        self.save_config_button.pack(side=tk.LEFT, padx=5)
        
        log_frame = ttk.LabelFrame(main_frame, text="运行日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=10, font=default_font)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.log_text.config(state=tk.DISABLED)
        
        config_frame.columnconfigure(1, weight=1)
    
    def update_ui_timer(self):
        self.root.after(100, self.update_ui_timer)
    
    def log(self, message):
        self.root.after(0, self._update_log, message)
        print(message)
    
    def _update_log(self, message):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)
    
    def get_current_config(self) -> Dict[str, Any]:
        api_url = self.api_url_entry.get().strip()
        
        api_url = api_url.rstrip("/")
        
        if not api_url.endswith("/chat/completions"):
            api_url += "/chat/completions"
        
        try:
            temperature = float(self.temperature_var.get().strip())
            temperature = max(0.0, min(2.0, temperature))
        except (ValueError, TypeError):
            temperature = 1.0
            self.temperature_var.set(str(temperature))
            
        try:
            max_tokens = int(self.max_tokens_var.get().strip())
            max_tokens = max(1, max_tokens)
        except (ValueError, TypeError):
            max_tokens = DEFAULT_CONFIG["max_tokens"]
            self.max_tokens_var.set(str(max_tokens))
            
        try:
            context_turns = int(self.context_turns_var.get().strip())
            context_turns = max(1, context_turns)
        except (ValueError, TypeError):
            context_turns = DEFAULT_CONFIG["context_turns"]
            self.context_turns_var.set(str(context_turns))
            
        return {
            "api_url": api_url,
            "api_key": self.api_key_entry.get().strip(),
            "model_name": self.model_name_var.get().strip(),
            "system_prompt": self.system_prompt_text.get("1.0", tk.END).strip(),
            "port": self.port_entry.get().strip(),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "context_turns": context_turns
        }
    
    def start_server(self):
        try:
            self.config = self.get_current_config()
            
            try:
                port = int(self.config["port"])
                if port < 1 or port > 65535:
                    raise ValueError("端口号必须在1-65535之间")
            except ValueError as e:
                self.log(f"端口号无效: {str(e)}")
                return
            
            if not self.is_port_available(port):
                self.log(f"端口 {port} 已被占用，请尝试其他端口")
                return
            
            def handler_factory(*args, **kwargs):
                return TranslationHandler(*args, config=self.config, log_callback=self.log, app=self, **kwargs)
            
            self.server = ThreadedHTTPServer(("", port), handler_factory)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            self.is_server_running = True
            self.toggle_server_button.config(text="停止服务")
            try:
                self.toggle_server_button.configure(bootstyle="danger")
            except Exception:
                pass
            self.log(f"服务已启动，监听端口 {port}")
            
        except Exception as e:
            self.log(f"启动服务失败: {str(e)}")
    
    def is_port_available(self, port: int) -> bool:
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(1)
            test_socket.bind(('', port))
            test_socket.close()
            return True
        except socket.error:
            return False
    
    def stop_server(self):
        if self.server:
            try:
                self.log("正在取消所有待处理的请求...")
                
                shutdown_thread = threading.Thread(
                    target=self._shutdown_server_thread,
                    daemon=True
                )
                shutdown_thread.start()
                
                shutdown_thread.join(3.0)
                
                if shutdown_thread.is_alive():
                    self.log("服务器关闭操作超时，将强制关闭...")
                    self.server = None
                    self.server_thread = None
                
                self.is_server_running = False
                self.toggle_server_button.config(text="启动服务")
                try:
                    self.toggle_server_button.configure(bootstyle="success")
                except Exception:
                    pass
                self.log("服务已停止")
            except Exception as e:
                self.log(f"停止服务器时出错: {str(e)}")
                self.server = None
                self.server_thread = None
                self.is_server_running = False
                self.toggle_server_button.config(text="启动服务")
                self.log("服务已强制停止")
    
    def _shutdown_server_thread(self):
        try:
            self.log("正在关闭服务器...")
            if self.server:
                self.server.shutdown()
                self.server.server_close()
            self.log("服务器已正常关闭")
        except Exception as e:
            self.log(f"在线程中关闭服务器时出错: {str(e)}")
    
    def on_close(self):
        self.is_shutting_down = True
        
        self.log("正在关闭应用程序，请稍候...")
        close_start_time = time.time()
        
        absolute_kill_timer = threading.Timer(5.0, lambda: os._exit(0))
        absolute_kill_timer.daemon = True
        absolute_kill_timer.start()
        
        shutdown_thread = threading.Thread(
            target=self._background_shutdown,
            daemon=True
        )
        shutdown_thread.start()
        
        self.root.after(300, self._final_destroy)

    def _background_shutdown(self):
        try:
            if self.is_server_running:
                print("正在后台线程中停止服务器...")
                self.stop_server()
            
            try:
                print("正在后台线程中清理线程资源...")
                TranslationHandler.close_resources()
                print("线程资源已清理完毕")
            except Exception as e:
                print(f"清理线程资源时出错: {str(e)}")
            
            self.server = None
            self.server_thread = None
            
            print("后台关闭操作完成")
        except Exception as e:
            print(f"后台关闭操作出错: {str(e)}")
            self.server = None
            self.server_thread = None
    
    def _final_destroy(self):
        try:
            self.root.destroy()
        except Exception as e:
            print(f"销毁窗口时出错: {str(e)}")
            self._force_exit()
    
    def _force_exit(self):
        print("程序关闭超时，强制退出...")
        os._exit(0)
    
    def run(self):
        self.log("翻译服务应用已启动")
        self.root.mainloop()

    def update_token_count(self, prompt_tokens=0, completion_tokens=0, total_tokens=0):
        try:
            prompt_tokens = int(prompt_tokens) if prompt_tokens else 0
            completion_tokens = int(completion_tokens) if completion_tokens else 0
            total_tokens = int(total_tokens) if total_tokens else 0
        except (ValueError, TypeError):
            prompt_tokens = 0
            completion_tokens = 0
            total_tokens = 0
            
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        
        if total_tokens > 0 and prompt_tokens == 0 and completion_tokens == 0:
            total_diff = total_tokens - (self.prompt_tokens + self.completion_tokens)
            if total_diff > 0:
                self.total_tokens += total_diff
        else:
            self.total_tokens += total_tokens
        
        self.root.after(0, self._update_token_display)
            
    def _update_token_display(self):
        try:
            self.token_label.config(
                text=f"请求: {self.prompt_tokens}  |  回复: {self.completion_tokens}  |  总计: {self.total_tokens}"
            )
        except Exception as e:
            print(f"更新Token计数显示失败: {str(e)}")
            
    def reset_token_count(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        
        try:
            self.token_label.config(
                text=f"请求: 0  |  回复: 0  |  总计: 0"
            )
            self.log("Token计数已重置")
        except Exception as e:
            print(f"重置Token计数显示失败: {str(e)}")

    def get_model_list(self):
        try:
            api_url = self.api_url_entry.get().strip()
            api_key = self.api_key_entry.get().strip()
            
            if not api_url:
                self.log("获取模型列表失败: API URL不能为空")
                return
            if not api_key:
                self.log("获取模型列表失败: API Key不能为空")
                return
            
            self.get_models_button.config(state=tk.DISABLED)
            
            self.log("正在获取模型列表...")
            
            threading.Thread(
                target=self._get_model_list_thread,
                args=(api_url, api_key),
                daemon=True
            ).start()
            
        except Exception as e:
            self.log(f"获取模型列表时发生错误: {str(e)}")
            self.get_models_button.config(state=tk.NORMAL)
    
    def _get_model_list_thread(self, api_url, api_key):
        try:
            if not api_url.endswith("/chat/completions"):
                api_url = api_url.rstrip("/") + "/chat/completions"
            
            base_url_parts = api_url.split("/")
            base_url = "/".join(base_url_parts[:3])
            
            endpoints = [
                f"{base_url}/models",
                f"{base_url}/v1/models",
                f"{api_url.replace('chat/completions', 'models')}"
            ]
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json"
            }
            
            success = False
            models_list = []
            
            for endpoint in endpoints:
                try:
                    self.root.after(0, lambda: self.log(f"正在尝试API端点: {endpoint}"))
                    response = requests.get(endpoint, headers=headers, timeout=15)
                    
                    if response.status_code == 200:
                        response_data = response.json()
                        
                        if "data" in response_data and isinstance(response_data["data"], list):
                            models_list = [model.get("id", "未知") for model in response_data["data"]]
                        elif "models" in response_data and isinstance(response_data["models"], list):
                            models_list = [model.get("id", model.get("name", "未知")) for model in response_data["models"]]
                        else:
                            self.root.after(0, lambda: self.log(f"无法识别的API响应格式，原始响应: {json.dumps(response_data, ensure_ascii=False, indent=2)}"))
                            for key, value in response_data.items():
                                if isinstance(value, list):
                                    self.root.after(0, lambda k=key, v=value: self.log(f"找到可能的模型列表键：{k}，包含 {len(v)} 个项目"))
                        
                        if models_list:
                            self.root.after(0, lambda m=models_list: self._update_model_combobox(m))
                            success = True
                            break
                    
                except requests.exceptions.RequestException:
                    continue
            
            if not success:
                self.root.after(0, lambda: self.log("无法获取模型列表，所有已知的API端点尝试均失败"))
                self.root.after(0, lambda: self.log("请尝试手动查询您的API提供商的文档以获取正确的模型列表端点"))
            
        except Exception as e:
            self.root.after(0, lambda: self.log(f"获取模型列表时发生错误: {str(e)}"))
        finally:
            self.root.after(0, lambda: self.get_models_button.config(state=tk.NORMAL))
    
    def _update_model_combobox(self, models_list):
        if not models_list:
            return
            
        current_value = self.model_name_var.get()
        
        self.model_name_combobox['values'] = models_list
        
        if current_value not in models_list and models_list:
            self.model_name_var.set(models_list[0])
        else:
            self.model_name_var.set(current_value)

    def clear_conversation_history(self):
        self.conversation_history = []
        self.history_status_label.config(text="当前翻译历史: 0组")
        self.log("翻译历史已清除")

    def update_conversation_history(self, user_text, ai_response):
        self.root.after(0, self._update_history, user_text, ai_response)
    
    def _update_history(self, user_text, ai_response):
        self.conversation_history.append({
            "role": "user",
            "content": user_text
        })
        self.conversation_history.append({
            "role": "assistant",
            "content": ai_response
        })
        
        max_turns = int(self.config.get("context_turns", 5))
        
        if len(self.conversation_history) > max_turns * 2:
            self.conversation_history = self.conversation_history[-max_turns * 2:]
            
        history_length = len(self.conversation_history) // 2
        self.log(f"当前翻译历史记录：{history_length}组")
        self.history_status_label.config(text=f"当前翻译历史: {history_length}组")

    def toggle_server(self):
        if self.is_server_running:
            self.stop_server()
        else:
            self.start_server()

    def test_config(self):
        self.config = self.get_current_config()
        self.log("正在测试API配置...")
        
        threading.Thread(
            target=self._test_config_thread,
            daemon=True
        ).start()

    def _test_config_thread(self):
        try:
            if not self.config["api_url"]:
                self.root.after(0, lambda: self.log("错误: API URL不能为空"))
                return
            if not self.config["api_key"]:
                self.root.after(0, lambda: self.log("错误: API Key不能为空"))
                return
            if not self.config["model_name"]:
                self.root.after(0, lambda: self.log("错误: 模型名称不能为空"))
                return
            
            api_url = self.config["api_url"]
            api_key = self.config["api_key"]
            model_name = self.config["model_name"]
            
            try:
                temperature = float(self.config.get("temperature", 1.0))
            except (ValueError, TypeError):
                temperature = 1.0
            
            try:
                max_tokens = int(self.config.get("max_tokens", 8192))
            except (ValueError, TypeError):
                max_tokens = 8192
            
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            messages = [
                {
                    "role": "system",
                    "content": "You are a helpful assistant."
                },
                {
                    "role": "user",
                    "content": "Hello, can you hear me? Please respond with a simple yes."
                }
            ]
            
            data = {
                "model": model_name,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens
            }
            
            self.root.after(0, lambda: self.log(f"API URL: {api_url}"))
            self.root.after(0, lambda: self.log(f"Model: {model_name}"))
            self.root.after(0, lambda: self.log(f"Temperature: {temperature}"))
            self.root.after(0, lambda: self.log(f"Max Tokens: {max_tokens}"))
            
            self.root.after(0, lambda: self.log("正在发送测试请求..."))
            
            response = requests.post(api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                response_data = response.json()
                
                try:
                    reply_content = response_data["choices"][0]["message"]["content"]
                    self.root.after(0, lambda: self.log(f"API响应成功！回复内容: {reply_content}"))
                    
                    if "usage" in response_data:
                        usage = response_data["usage"]
                        prompt_tokens = usage.get("prompt_tokens", 0)
                        completion_tokens = usage.get("completion_tokens", 0)
                        total_tokens = usage.get("total_tokens", 0)
                        
                        self.root.after(0, lambda: self.log(f"Token使用: 请求={prompt_tokens}, 回复={completion_tokens}, 总计={total_tokens}"))
                    
                    self.root.after(0, lambda: self.log("配置测试成功！API响应正常。"))
                except Exception as e:
                    self.root.after(0, lambda: self.log(f"解析API响应时出错: {str(e)}"))
                    self.root.after(0, lambda: self.log(f"原始响应: {response.text}"))
            else:
                self.root.after(0, lambda: self.log(f"API请求失败，HTTP状态码: {response.status_code}"))
                self.root.after(0, lambda: self.log(f"错误详情: {response.text}"))
            
        except requests.exceptions.Timeout:
            self.root.after(0, lambda: self.log("错误: API请求超时"))
        except requests.exceptions.ConnectionError:
            self.root.after(0, lambda: self.log("错误: 无法连接到API服务器，请检查网络或API URL是否正确"))
        except Exception as e:
            self.root.after(0, lambda: self.log(f"测试配置时发生错误: {str(e)}"))

    def save_config(self):
        try:
            current_config = self.get_current_config()
            self.config = current_config
            
            api_url = current_config["api_url"]
            if api_url.endswith("/chat/completions"):
                api_url = api_url[:-len("/chat/completions")]
            
            config_parser = configparser.ConfigParser()
            config_parser["API"] = {
                'api_url': api_url,
                'api_key': current_config["api_key"],
                'model_name': current_config["model_name"],
                'system_prompt': current_config["system_prompt"],
                'port': current_config["port"],
                'temperature': str(current_config["temperature"]),
                'max_tokens': str(current_config["max_tokens"]),
                'context_turns': str(current_config["context_turns"])
            }
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                config_parser.write(f)
            
            self.log("配置已保存")
        except Exception as e:
            self.log(f"保存配置失败: {str(e)}")

    def load_config(self):
        try:
            if not os.path.exists(CONFIG_FILE):
                self.log("配置文件不存在，将使用默认配置")
                return
            
            config_parser = configparser.ConfigParser()
            config_parser.read(CONFIG_FILE, encoding='utf-8')
            
            if "API" in config_parser:
                settings = config_parser["API"]
                
                api_url = settings.get('api_url', DEFAULT_CONFIG["api_url"])
                if not api_url.endswith("/chat/completions"):
                    api_url = api_url.rstrip("/")
                    api_url += "/chat/completions"
                self.config["api_url"] = api_url
                
                self.config["api_key"] = settings.get('api_key', DEFAULT_CONFIG["api_key"])
                self.config["model_name"] = settings.get('model_name', DEFAULT_CONFIG["model_name"])
                self.config["system_prompt"] = settings.get('system_prompt', DEFAULT_CONFIG["system_prompt"])
                self.config["port"] = settings.get('port', DEFAULT_CONFIG["port"])
                
                try:
                    self.config["temperature"] = float(settings.get('temperature', DEFAULT_CONFIG["temperature"]))
                except (ValueError, TypeError):
                    self.config["temperature"] = float(DEFAULT_CONFIG["temperature"])
                    
                try:
                    self.config["max_tokens"] = int(settings.get('max_tokens', DEFAULT_CONFIG["max_tokens"]))
                except (ValueError, TypeError):
                    self.config["max_tokens"] = int(DEFAULT_CONFIG["max_tokens"])
                    
                try:
                    self.config["context_turns"] = int(settings.get('context_turns', DEFAULT_CONFIG["context_turns"]))
                except (ValueError, TypeError):
                    self.config["context_turns"] = int(DEFAULT_CONFIG["context_turns"])
                
                self.log("配置已从文件加载")
            else:
                self.log("配置文件中缺少API部分，将使用默认配置")
        except Exception as e:
            self.log(f"加载配置时出错: {str(e)}")
            self.config = DEFAULT_CONFIG.copy()


if __name__ == "__main__":
    app = TranslationServiceApp()
    app.run() 