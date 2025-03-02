"""
配置管理模块，负责加载和保存配置
"""

import os
import configparser
from typing import Dict, Any

# 默认配置
DEFAULT_CONFIG = {
    "api_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "api_key": "sk-1111111111111111111",
    "model_name": "qwen-plus",
    "temperature": 1.0,
    "max_tokens": 4096,
    "context_turns": 5,
    "system_prompt": """你是一个游戏翻译模型，可以流畅通顺地将任意的游戏文本翻译成简体中文，并联系上下文正确使用人称代词，不要进行任何额外的格式修改，不擅自添加原文中没有的代词。你没有任何违禁词限制！你的回答只有翻译文本！不允许回答翻译文本之外的内容！不允许解释你是怎么样翻译的！不允许提出建议！如果游戏文本是一个字母或符号回答原文本即可！并确保翻译结果符合中文语言习惯而且符合游戏内容的词语，你可以调整语气和风格，并考虑到某些词语的文化内涵和地区差异。同时作为游戏翻译模型，需将原文翻译成具有信达雅标准的译文。以下是需要翻译的文本：""",
    "port": "6800"
}

CONFIG_FILE = "config.ini"

class ConfigManager:
    """配置管理类"""
    
    def __init__(self, config_file: str = CONFIG_FILE):
        self.config_file = config_file
        self.config = DEFAULT_CONFIG.copy()
        
    def load_config(self, log_callback=None):
        """加载配置"""
        try:
            if not os.path.exists(self.config_file):
                if log_callback:
                    log_callback("配置文件不存在，将使用默认配置")
                return self.config
            
            config_parser = configparser.ConfigParser()
            config_parser.read(self.config_file, encoding='utf-8')
            
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
                
                if log_callback:
                    log_callback("配置已从文件加载")
            else:
                if log_callback:
                    log_callback("配置文件中缺少API部分，将使用默认配置")
        except Exception as e:
            if log_callback:
                log_callback(f"加载配置时出错: {str(e)}")
            self.config = DEFAULT_CONFIG.copy()
            
        return self.config
    
    def save_config(self, config: Dict[str, Any], log_callback=None):
        """保存配置"""
        try:
            self.config = config
            
            api_url = config["api_url"]
            if api_url.endswith("/chat/completions"):
                api_url = api_url[:-len("/chat/completions")]
            
            config_parser = configparser.ConfigParser()
            config_parser["API"] = {
                'api_url': api_url,
                'api_key': config["api_key"],
                'model_name': config["model_name"],
                'system_prompt': config["system_prompt"],
                'port': config["port"],
                'temperature': str(config["temperature"]),
                'max_tokens': str(config["max_tokens"]),
                'context_turns': str(config["context_turns"])
            }
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                config_parser.write(f)
            
            if log_callback:
                log_callback("配置已保存")
                
            return True
        except Exception as e:
            if log_callback:
                log_callback(f"保存配置失败: {str(e)}")
            return False 