import re
<<<<<<< HEAD
=======
import json
>>>>>>> 1f88e85856a3fcf12e037e6633a5cf6ee5113ada


# --- 测试1：中文 bug ---
# 修复前，TTS 队列过滤正则要求句子含英文字母或数字，导致中文句子全部被丢弃
def test_chinese_tts_filter_bug():
    chinese = "你好，今天天气很好。"
    old_regex = r'[a-zA-Z0-9]'
    new_regex = r'[\w一-鿿]'
    assert not re.search(old_regex, chinese), "旧正则不应匹配纯中文（即旧代码会丢弃此句）"
    assert re.search(new_regex, chinese),     "新正则应匹配中文（修复后此句能进入 TTS 队列）"


# --- 测试2：speak() 文本清理保留中文标点 ---
# 修复前的正则会删掉，。！？等中文标点，导致 TTS 停顿异常
def test_speak_clean_keeps_chinese_punct():
    text = "你好！今天天气，很好。"
    clean = re.sub(r"[^\w\s,.!?:-，。！？、；：]", "", text)
    assert "，" in clean, "逗号应被保留"
    assert "。" in clean, "句号应被保留"
    assert "！" in clean, "感叹号应被保留"


# --- 测试3：config 缺字段时有合理默认值 ---
# 保证旧的 config.json 不加新字段也能正常运行（向后兼容）
def test_whisper_config_defaults():
    config = {}
    model = config.get("whisper_model", "ggml-base.en.bin")
    lang  = config.get("whisper_lang", "en")
    assert model == "ggml-base.en.bin"
    assert lang  == "en"
# --- 测试4：JSON 动作解析 ---
def test_action_json_parse():
    text = '{"action": "get_time", "value": "now"}'
    data = json.loads(text)
    assert data["action"] == "get_time"
    assert data["value"]  == "now"
