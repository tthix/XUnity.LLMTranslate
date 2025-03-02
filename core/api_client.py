"""
API客户端模块，负责与大模型API通信
"""

import re
import requests
from typing import Dict, Any, List, Optional, Callable

class APIClient:
    """API客户端类"""
    
    def __init__(self, config: Dict[str, Any], log_callback: Optional[Callable] = None):
        """
        初始化API客户端
        
        Args:
            config: 配置信息
            log_callback: 日志回调函数
        """
        self.config = config
        self.log_callback = log_callback
    
    def translate_text(self, text: str, conversation_history: List[Dict[str, str]] = None) -> Dict[str, Any]:
        """
        翻译文本
        
        Args:
            text: 要翻译的文本
            conversation_history: 对话历史记录
            
        Returns:
            包含翻译结果和统计信息的字典
        """
        if not text or text.strip() == "":
            if self.log_callback:
                self.log_callback("错误: 输入文本为空")
            return {"success": False, "text": "翻译失败: 输入文本为空"}

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
            if self.log_callback:
                self.log_callback("错误: API配置不完整，请检查API URL、API Key和模型名称")
            return {"success": False, "text": "翻译失败: API配置不完整"}
        
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
        
        if conversation_history:
            if self.log_callback:
                history_length = len(conversation_history) // 2
                self.log_callback(f"使用当前翻译上下文记录: {history_length}组")
            messages.extend(conversation_history)
        
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
        
        if self.log_callback:
            self.log_callback(f"正在发送翻译请求到API... (Temperature: {temperature}, Max Tokens: {max_tokens})")
        
        try:
            response = requests.post(api_url, headers=headers, json=data, timeout=180)
        except requests.exceptions.Timeout:
            if self.log_callback:
                self.log_callback("错误: API请求超时")
            return {"success": False, "text": "翻译失败: API请求超时"}
        except requests.exceptions.ConnectionError:
            if self.log_callback:
                self.log_callback("错误: 无法连接到API服务器")
            return {"success": False, "text": "翻译失败: 无法连接到API服务器"}
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"API请求发生错误: {str(e)}")
            return {"success": False, "text": f"翻译失败: {str(e)}"}
        
        if response.status_code != 200:
            if self.log_callback:
                self.log_callback(f"API请求失败，状态码: {response.status_code}, 原因: {response.text}")
            return {"success": False, "text": f"翻译失败: API返回错误码 {response.status_code}"}
        
        try:
            response_data = response.json()
            if self.log_callback:
                self.log_callback("收到API响应")
            
            translated_text = response_data["choices"][0]["message"]["content"]
            
            usage = {}
            if "usage" in response_data:
                usage = response_data["usage"]
                
            if not translated_text or translated_text.strip() == "":
                if self.log_callback:
                    self.log_callback("警告: API返回了空的翻译结果")
                return {"success": False, "text": "翻译失败: API返回了空的翻译结果"}
            
            original_length = len(translated_text)
            
            translated_text = re.sub(r'<thinking>.*?</thinking>', '', translated_text, flags=re.DOTALL|re.IGNORECASE)
            translated_text = re.sub(r'<think>.*?</think>', '', translated_text, flags=re.DOTALL|re.IGNORECASE)
            translated_text = re.sub(r'<think(?:ing)?>[^<]*(?:</think(?:ing)?>)?', '', translated_text, flags=re.DOTALL|re.IGNORECASE)
            
            translated_text = re.sub(r'\n\s*\n', '\n\n', translated_text)
            translated_text = translated_text.strip()
            
            if len(translated_text) != original_length and self.log_callback:
                self.log_callback(f"已移除思维链内容 (减少了{original_length - len(translated_text)}个字符)")
            
            max_length = 10000
            if len(translated_text) > max_length:
                if self.log_callback:
                    self.log_callback(f"警告: 翻译结果过长，已截断至{max_length}字符")
                translated_text = translated_text[:max_length] + "...(内容过长已截断)"
            
            return {
                "success": True, 
                "text": translated_text, 
                "usage": usage
            }
        except (KeyError, IndexError) as e:
            if self.log_callback:
                self.log_callback(f"解析API响应失败: {str(e)}, 响应: {response_data}")
            return {"success": False, "text": "翻译失败: 无法解析API响应"}
        except Exception as e:
            if self.log_callback:
                self.log_callback(f"处理API响应时发生错误: {str(e)}")
            return {"success": False, "text": f"翻译失败: {str(e)}"}
    
    def test_connection(self) -> Dict[str, Any]:
        """
        测试API连接
        
        Returns:
            测试结果字典
        """
        api_url = self.config.get("api_url")
        api_key = self.config.get("api_key")
        model_name = self.config.get("model_name")
        
        if not api_url:
            return {"success": False, "message": "错误: API URL不能为空"}
        if not api_key:
            return {"success": False, "message": "错误: API Key不能为空"}
        if not model_name:
            return {"success": False, "message": "错误: 模型名称不能为空"}
        
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
        
        if self.log_callback:
            self.log_callback(f"API URL: {api_url}")
            self.log_callback(f"Model: {model_name}")
            self.log_callback(f"Temperature: {temperature}")
            self.log_callback(f"Max Tokens: {max_tokens}")
            self.log_callback("正在发送测试请求...")
        
        try:
            response = requests.post(api_url, headers=headers, json=data, timeout=30)
            
            if response.status_code == 200:
                response_data = response.json()
                
                try:
                    reply_content = response_data["choices"][0]["message"]["content"]
                    result = {
                        "success": True,
                        "message": f"API响应成功！回复内容: {reply_content}",
                        "content": reply_content
                    }
                    
                    if "usage" in response_data:
                        usage = response_data["usage"]
                        prompt_tokens = usage.get("prompt_tokens", 0)
                        completion_tokens = usage.get("completion_tokens", 0)
                        total_tokens = usage.get("total_tokens", 0)
                        
                        result["usage"] = {
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total_tokens
                        }
                        
                        if self.log_callback:
                            self.log_callback(f"Token使用: 请求={prompt_tokens}, 回复={completion_tokens}, 总计={total_tokens}")
                    
                    if self.log_callback:
                        self.log_callback("配置测试成功！API响应正常。")
                    
                    return result
                except Exception as e:
                    return {
                        "success": False,
                        "message": f"解析API响应时出错: {str(e)}",
                        "raw_response": response.text
                    }
            else:
                return {
                    "success": False,
                    "message": f"API请求失败，HTTP状态码: {response.status_code}",
                    "error_details": response.text
                }
        except requests.exceptions.Timeout:
            return {"success": False, "message": "错误: API请求超时"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "错误: 无法连接到API服务器，请检查网络或API URL是否正确"}
        except Exception as e:
            return {"success": False, "message": f"测试配置时发生错误: {str(e)}"}
    
    def get_model_list(self) -> Dict[str, Any]:
        """
        获取模型列表
        
        Returns:
            包含模型列表的字典
        """
        api_url = self.config.get("api_url", "")
        api_key = self.config.get("api_key", "")
        
        if not api_url:
            return {"success": False, "message": "获取模型列表失败: API URL不能为空"}
        if not api_key:
            return {"success": False, "message": "获取模型列表失败: API Key不能为空"}
        
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
                if self.log_callback:
                    self.log_callback(f"正在尝试API端点: {endpoint}")
                response = requests.get(endpoint, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    response_data = response.json()
                    
                    if "data" in response_data and isinstance(response_data["data"], list):
                        models_list = [model.get("id", "未知") for model in response_data["data"]]
                    elif "models" in response_data and isinstance(response_data["models"], list):
                        models_list = [model.get("id", model.get("name", "未知")) for model in response_data["models"]]
                    else:
                        if self.log_callback:
                            import json
                            self.log_callback(f"无法识别的API响应格式，原始响应: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
                        for key, value in response_data.items():
                            if isinstance(value, list):
                                if self.log_callback:
                                    self.log_callback(f"找到可能的模型列表键：{key}，包含 {len(value)} 个项目")
                    
                    if models_list:
                        success = True
                        break
                
            except requests.exceptions.RequestException:
                continue
        
        if not success:
            if self.log_callback:
                self.log_callback("无法获取模型列表，所有已知的API端点尝试均失败")
                self.log_callback("请尝试手动查询您的API提供商的文档以获取正确的模型列表端点")
            return {"success": False, "message": "无法获取模型列表，请检查API配置"}
        
        return {"success": True, "models": models_list} 