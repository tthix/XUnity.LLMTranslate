import tkinter as tk
from tkinter import scrolledtext
import ttkbootstrap as ttk
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import threading
import urllib.parse
import configparser
from openai import OpenAI
import queue
from collections import deque
import hashlib

class ConfigManager:
    """配置管理器，负责配置文件的读写操作"""
    def __init__(self, filename='config.ini'):
        self.filename = filename
        self.config = configparser.ConfigParser()
        self.config.read(filename)

    def save_config(self, settings):
        """保存配置到文件"""
        if not self.config.has_section('Settings'):
            self.config.add_section('Settings')
        for key, value in settings.items():
            self.config.set('Settings', key, str(value))
        with open(self.filename, 'w') as f:
            self.config.write(f)

    def load_config(self):
        """从文件加载配置，返回默认配置字典"""
        default_prompt = """你是一个游戏翻译模型，可以流畅通顺地将任意的游戏文本翻译成简体中文..."""
        
        return {
            'api_address': self.config.get('Settings', 'api_address', fallback='https://api.openai.com/v1'),
            'api_key': self.config.get('Settings', 'api_key', fallback=''),
            'model_name': self.config.get('Settings', 'model_name', fallback='gpt-3.5-turbo'),
            'port': self.config.get('Settings', 'port', fallback='6800'),
            'system_prompt': self.config.get('Settings', 'system_prompt', fallback=default_prompt),
            'pre_prompt': self.config.get('Settings', 'pre_prompt', fallback='将下面的文本翻译成简体中文：'),
            'context_num': self.config.getint('Settings', 'context_num', fallback=5)
        }

class TranslationHandler(BaseHTTPRequestHandler):
    _contexts = {}  # 客户端上下文存储字典
    _lock = threading.Lock()  # 全局锁

    def __init__(self, get_config_func, log_queue, *args, **kwargs):
        self.get_config = get_config_func
        self.log_queue = log_queue
        super().__init__(*args, **kwargs)

    def get_client_id(self):
        """生成唯一客户端标识"""
        client_ip = self.client_address[0]
        return hashlib.md5(client_ip.encode()).hexdigest()[:8]

    def do_GET(self):
        """处理GET请求"""
        try:
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)

            if parsed.path != "/":
                self.send_response(404)
                self.send_header('Content-type', 'text/plain; charset=utf-8')
                self.end_headers()
                self.wfile.write("404 Not Found".encode('utf-8'))
                return

            text = query.get('text', [''])[0].strip()
            if not text:
                self.send_response(200)
                self.end_headers()
                return

            self.log_queue.put(f"收到请求: {text}")

            config = self.get_config()
            client = OpenAI(
                base_url=config['api_address'],
                api_key=config['api_key']
            )

            # 获取或创建客户端上下文
            client_id = self.get_client_id()
            with self._lock:
                if client_id not in self._contexts:
                    self._contexts[client_id] = {
                        'queue': deque(maxlen=config['context_num']),
                        'maxlen': config['context_num']
                    }
                else:
                    # 动态调整队列长度
                    if self._contexts[client_id]['maxlen'] != config['context_num']:
                        new_queue = deque(
                            self._contexts[client_id]['queue'],
                            maxlen=config['context_num']
                        )
                        self._contexts[client_id] = {
                            'queue': new_queue,
                            'maxlen': config['context_num']
                        }

            # 构建消息列表
            messages = [{"role": "system", "content": config['system_prompt']}]
            
            # 添加上下文历史
            with self._lock:
                for user_content, assistant_content in self._contexts[client_id]['queue']:
                    messages.append({"role": "user", "content": user_content})
                    messages.append({"role": "assistant", "content": assistant_content})

            # 添加当前请求
            current_user_content = f"{config['pre_prompt']}{text}"
            messages.append({"role": "user", "content": current_user_content})

            # 调试日志
            self.log_queue.put(f"当前上下文数: {len(self._contexts[client_id]['queue'])}")
            self.log_queue.put(f"完整消息列表: {messages}")

            response = client.chat.completions.create(
                model=config['model_name'],
                messages=messages
            )

            translated = response.choices[0].message.content

            # 更新上下文队列
            with self._lock:
                self._contexts[client_id]['queue'].append(
                    (current_user_content, translated)
                )

            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(translated.encode('utf-8'))
            self.log_queue.put(f"翻译结果: {translated}")

        except Exception as e:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(f"服务器错误: {str(e)}".encode('utf-8'))
            self.log_queue.put(f"处理错误: {str(e)}")

    @classmethod
    def create_handler(cls, get_config_func, log_queue):
        return lambda *args, **kwargs: cls(get_config_func, log_queue, *args, **kwargs)

class TranslationApp:
    """主应用程序GUI"""
    def __init__(self, master):
        self.master = master
        self.master.title("XUnity大模型翻译GUI")
        self.config = ConfigManager().load_config()
        self.log_queue = queue.Queue()
        self.server = None
        self.create_widgets()
        self.load_config()
        self.update_log()

    def create_widgets(self):
        """创建界面组件"""
        style = ttk.Style(theme='flatly')
        main_frame = ttk.Frame(self.master)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # 配置区域
        config_frame = ttk.LabelFrame(main_frame, text="API配置")
        config_frame.grid(row=0, column=0, sticky="nsew", pady=5)

        # 基础配置项
        entries = [
            ('API地址:', 'api_address', 0),
            ('API密钥:', 'api_key', 1),
            ('模型名称:', 'model_name', 2),
            ('监听端口:', 'port', 3),
        ]
        
        for text, var_name, row in entries:
            ttk.Label(config_frame, text=text).grid(row=row, column=0, sticky="e", pady=2)
            entry = ttk.Entry(config_frame)
            entry.grid(row=row, column=1, padx=5, pady=2, sticky="ew")
            setattr(self, var_name, entry)

        # 系统提示框
        ttk.Label(config_frame, text="系统提示:").grid(row=4, column=0, sticky="ne", pady=2)
        self.system_prompt = scrolledtext.ScrolledText(config_frame, height=8, wrap=tk.WORD)
        self.system_prompt.grid(row=4, column=1, padx=5, pady=5, sticky="nsew")

        # 前置文本框
        ttk.Label(config_frame, text="前置文本:").grid(row=5, column=0, sticky="e", pady=2)
        self.pre_prompt = ttk.Entry(config_frame)
        self.pre_prompt.grid(row=5, column=1, padx=5, pady=2, sticky="ew")

        # 上下文数量设置
        ttk.Label(config_frame, text="上下文数量:").grid(row=6, column=0, sticky="e", pady=2)
        self.context_num = ttk.Spinbox(config_frame, from_=0, to=10, width=5)
        self.context_num.grid(row=6, column=1, padx=5, pady=2, sticky="w")

        # 按钮区域
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=1, column=0, pady=5, sticky="ew")
        
        buttons = [
            ('启动服务', self.start_server),
            ('停止服务', self.stop_server),
            ('测试配置', self.test_config),
            ('保存配置', self.save_config),
        ]
        
        for text, cmd in buttons:
            btn = ttk.Button(btn_frame, text=text, command=cmd)
            btn.pack(side="left", padx=5)
            if text == '停止服务':
                self.stop_btn = btn
                btn.config(state="disabled")

        # 日志区域
        log_frame = ttk.LabelFrame(main_frame, text="运行日志")
        log_frame.grid(row=2, column=0, sticky="nsew", pady=5)
        self.log_area = scrolledtext.ScrolledText(log_frame, height=10, state="disabled")
        self.log_area.pack(fill=tk.BOTH, expand=True)

        # 布局权重配置
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        config_frame.columnconfigure(1, weight=1)
        config_frame.rowconfigure(4, weight=1)

    def load_config(self):
        """加载配置到界面"""
        self.api_address.insert(0, self.config['api_address'])
        self.api_key.insert(0, self.config['api_key'])
        self.model_name.insert(0, self.config['model_name'])
        self.port.insert(0, self.config['port'])
        self.pre_prompt.insert(0, self.config['pre_prompt'])
        self.system_prompt.insert('1.0', self.config['system_prompt'])
        self.context_num.set(self.config['context_num'])

    def get_config(self):
        """从界面获取当前配置"""
        try:
            context_num = int(self.context_num.get())
        except ValueError:
            context_num = 5
            
        return {
            'api_address': self.api_address.get(),
            'api_key': self.api_key.get(),
            'model_name': self.model_name.get(),
            'port': self.port.get(),
            'pre_prompt': self.pre_prompt.get(),
            'system_prompt': self.system_prompt.get('1.0', 'end-1c'),
            'context_num': context_num
        }

    def start_server(self):
        """启动HTTP服务"""
        config = self.get_config()
        try:
            self.server = ThreadingHTTPServer(
                ('localhost', int(config['port'])),
                TranslationHandler.create_handler(lambda: self.get_config(), self.log_queue)
            )
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            self.toggle_controls(True)
            self.log_queue.put(f"服务已启动，端口：{config['port']}")
        except Exception as e:
            self.log_queue.put(f"启动失败：{str(e)}")

    def stop_server(self):
        """停止HTTP服务"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            self.toggle_controls(False)
            self.log_queue.put("服务已停止")

    def test_config(self):
        """测试API连接配置"""
        try:
            client = OpenAI(
                base_url=self.api_address.get(),
                api_key=self.api_key.get()
            )
            client.chat.completions.create(
                model=self.model_name.get(),
                messages=[{"role": "user", "content": "测试连接"}]
            )
            self.log_queue.put("配置测试成功！")
        except Exception as e:
            self.log_queue.put(f"配置测试失败：{str(e)}")

    def save_config(self):
        """保存当前配置"""
        ConfigManager().save_config(self.get_config())
        self.log_queue.put("配置已保存")

    def toggle_controls(self, running):
        """切换控件状态"""
        state = "disabled" if running else "normal"
        self.stop_btn.config(state="normal" if running else "disabled")
        
        for widget in [self.api_address, self.api_key, self.model_name, 
                      self.port, self.pre_prompt, self.system_prompt, self.context_num]:
            widget.config(state=state)

    def update_log(self):
        """更新日志显示"""
        while not self.log_queue.empty():
            msg = self.log_queue.get()
            self.log_area.config(state="normal")
            self.log_area.insert(tk.END, msg + "\n")
            self.log_area.see(tk.END)
            self.log_area.config(state="disabled")
        self.master.after(100, self.update_log)

if __name__ == "__main__":
    root = ttk.Window()
    app = TranslationApp(root)
    root.mainloop()