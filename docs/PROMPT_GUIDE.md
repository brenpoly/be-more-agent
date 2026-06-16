# 二、prompts.py — 系统提示词

只放提示词文本，依赖 `config.CURRENT_CONFIG`。档2 的“每状态窄 prompt + few-shot”都加在这里，让负责调 prompt 的人独占此文件、不与改 `agent.py` 的人冲突。

| 名称 | 含义 |
|------|------|
| `BASE_SYSTEM_PROMPT` | 内置兜底人设：睡前情绪梳理、温和简短、只接住不出主意，并包含安全边界 |
| `CHAT_STAGE_PROMPT` | CHAT 阶段窄 prompt：只回应用户这一句，先接住情绪，再寄存到明天 |
| `CHAT_FEW_SHOTS` | few-shot 示例：工作压力、人际冲突、后悔自责、索要方案、自然收尾 |
| `NEAR_END_PROMPT` | 倒数第二轮提示：减少追问，开始自然收束 |
| `FINAL_ROUND_PROMPT` | 最后一轮提示：必须收尾，引导放松休息 |
| `SYSTEM_PROMPT` | **实际生效的系统提示** = `config.json` 的 `system_prompt`（无则用兜底）+ `system_prompt_extras` |

用法：

```python
from prompts import SYSTEM_PROMPT
messages = [{"role": "system", "content": SYSTEM_PROMPT}, ...]
```

睡前状态机中应优先使用带轮次信息的版本：

```python
from prompts import get_chat_prompt
chat_system = get_chat_prompt(round_num, max_rounds)
```
