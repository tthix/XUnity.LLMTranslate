"""
工具函数模块，包含一些通用的工具函数
"""

# 中文标点符号转英文标点符号映射
PUNCTUATION_MAPPING = {
    '，': ',', '。': '.', '！': '!', '？': '?', '；': ';', '：': ':',
    '"': '"', '"': '"', ''': "'", ''': "'", '【': '[', '】': ']',
    '（': '(', '）': ')', '《': '<', '》': '>', '、': ',', '～': '~'
}

def convert_punctuation(text: str) -> str:
    """
    转换中文标点为英文标点
    """
    if not text:
        return ""
    
    for cn_punct, en_punct in PUNCTUATION_MAPPING.items():
        text = text.replace(cn_punct, en_punct)
    
    return text 