"""
HTTP服务器模块，提供翻译服务的HTTP接口
"""

import http.server
import socketserver
import urllib.parse
import queue
import threading
import time
import concurrent.futures
import socket
from typing import Dict, Any, Callable, Optional, List

from core.utils import convert_punctuation

class TranslationHandler(http.server.BaseHTTPRequestHandler):
    """翻译请求处理类"""
    
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
    
    def __init__(self, *args, config=None, log_callback=None, app=None, api_client=None, **kwargs):
        self.config = config
        self.log_callback = log_callback
        self.app = app
        self.api_client = api_client
        self.result_queue = queue.Queue()
        super().__init__(*args, **kwargs)
    
    @classmethod
    def close_resources(cls):
        """关闭资源"""
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
    
    def log_message(self, format, *args):
        """日志记录"""
        message = f"{self.address_string()} - {format % args}"
        if self.log_callback:
            self.log_callback(message)
    
    def update_conversation_history(self, user_text, ai_response):
        """更新对话历史"""
        if self.app:
            self.app.update_conversation_history(user_text, ai_response)
    
    def do_GET(self):
        """处理GET请求"""
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
            
            translated_text = convert_punctuation(translated_text)
            
            self.wfile.write(translated_text.encode('utf-8'))
            self.log_callback(f"翻译完成: {translated_text[:50]}...")
            
        except Exception as e:
            self.log_callback(f"处理请求时出错: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()
            self.wfile.write(f"服务器错误: {str(e)}".encode('utf-8'))
    
    def _process_translation_request(self, text):
        """处理翻译请求"""
        try:
            if self.app and getattr(self.app, 'is_shutting_down', False):
                self.log_callback("应用程序正在关闭，取消翻译请求")
                self.result_queue.put("翻译失败: 应用程序正在关闭")
                return
            
            # 使用API客户端翻译文本
            if self.api_client:
                conversation_history = self.app.conversation_history if self.app else None
                result = self.api_client.translate_text(text, conversation_history)
                
                if result["success"]:
                    translated_text = result["text"]
                    
                    # 更新token计数
                    if "usage" in result and self.app:
                        usage = result["usage"]
                        prompt_tokens = usage.get("prompt_tokens", 0)
                        completion_tokens = usage.get("completion_tokens", 0)
                        total_tokens = usage.get("total_tokens", 0)
                        
                        self.app.update_token_count(prompt_tokens, completion_tokens, total_tokens)
                    
                    # 更新对话历史
                    self.update_conversation_history(text, translated_text)
                else:
                    translated_text = result["text"]  # 这里是错误信息
            else:
                self.log_callback("错误: API客户端未初始化")
                translated_text = "翻译失败: API客户端未初始化"
                
            if self.app and getattr(self.app, 'is_shutting_down', False):
                self.log_callback("应用程序正在关闭，放弃返回翻译结果")
                return
            
            self.result_queue.put(translated_text)
        except Exception as e:
            error_message = f"翻译失败: {str(e)}"
            self.log_callback(f"翻译处理异常: {str(e)}")
            if not (self.app and getattr(self.app, 'is_shutting_down', False)):
                self.result_queue.put(error_message)


class ThreadedHTTPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    """多线程HTTP服务器"""
    
    allow_reuse_address = True
    daemon_threads = True
    
    def shutdown(self):
        """关闭服务器"""
        try:
            super().shutdown()
        except Exception as e:
            print(f"服务器关闭时出错: {str(e)}")


class ServerManager:
    """服务器管理类"""
    
    def __init__(self, config, log_callback=None, app=None, api_client=None):
        """
        初始化服务器管理类
        
        Args:
            config: 配置信息
            log_callback: 日志回调函数
            app: 应用程序实例
            api_client: API客户端实例
        """
        self.config = config
        self.log_callback = log_callback
        self.app = app
        self.api_client = api_client
        self.server = None
        self.server_thread = None
        self.is_running = False
    
    def is_port_available(self, port: int) -> bool:
        """检查端口是否可用"""
        try:
            test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            test_socket.settimeout(1)
            test_socket.bind(('', port))
            test_socket.close()
            return True
        except socket.error:
            return False
    
    def start(self) -> bool:
        """启动服务器"""
        if self.is_running:
            if self.log_callback:
                self.log_callback("服务已经在运行中")
            return False
        
        try:
            try:
                port = int(self.config.get("port", 6800))
                if port < 1 or port > 65535:
                    raise ValueError("端口号必须在1-65535之间")
            except ValueError as e:
                if self.log_callback:
                    self.log_callback(f"端口号无效: {str(e)}")
                return False
            
            if not self.is_port_available(port):
                if self.log_callback:
                    self.log_callback(f"端口 {port} 已被占用，请尝试其他端口")
                return False
            
            def handler_factory(*args, **kwargs):
                return TranslationHandler(
                    *args, 
                    config=self.config, 
                    log_callback=self.log_callback, 
                    app=self.app,
                    api_client=self.api_client,
                    **kwargs
                )
            
            self.server = ThreadedHTTPServer(("", port), handler_factory)
            self.server_thread = threading.Thread(target=self.server.serve_forever)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            self.is_running = True
            
            if self.log_callback:
                self.log_callback(f"服务已启动，监听端口 {port}")
            
            return True
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"启动服务失败: {str(e)}")
            return False
    
    def stop(self) -> bool:
        """停止服务器"""
        if not self.is_running or not self.server:
            if self.log_callback:
                self.log_callback("服务未在运行")
            return False
        
        try:
            if self.log_callback:
                self.log_callback("正在取消所有待处理的请求...")
            
            shutdown_thread = threading.Thread(
                target=self._shutdown_server_thread,
                daemon=True
            )
            shutdown_thread.start()
            
            shutdown_thread.join(3.0)
            
            if shutdown_thread.is_alive():
                if self.log_callback:
                    self.log_callback("服务器关闭操作超时，将强制关闭...")
                self.server = None
                self.server_thread = None
            
            self.is_running = False
            
            if self.log_callback:
                self.log_callback("服务已停止")
            
            return True
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"停止服务器时出错: {str(e)}")
            self.server = None
            self.server_thread = None
            self.is_running = False
            
            if self.log_callback:
                self.log_callback("服务已强制停止")
            
            return True
    
    def _shutdown_server_thread(self):
        """关闭服务器的线程方法"""
        try:
            if self.log_callback:
                self.log_callback("正在关闭服务器...")
            if self.server:
                self.server.shutdown()
                self.server.server_close()
            if self.log_callback:
                self.log_callback("服务器已正常关闭")
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"在线程中关闭服务器时出错: {str(e)}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取服务器状态"""
        return {
            "is_running": self.is_running,
            "port": self.config.get("port", "未设置")
        } 