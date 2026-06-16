# flow.py · 睡前情绪梳理状态机

## 一、设计目标

将原来的"开放式问答"主循环收窄为一条**单向状态机**，引导用户完成从开机到入睡的完整流程。全程不需要唤醒词、不需要按键交互，是"插上电源就开始"的线性体验。

## 二、状态流转图

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ┌──────┐   ┌──────┐   ┌──────────┐   ┌──────┐   ┌───────┐   ┌──────────┐
│  │ BOOT │──▶│ CHAT │──▶│TRANSITION│──▶│AUDIO │──▶│ SLEEP │──▶│ SHUTDOWN │
│  └──────┘   └──────┘   └──────────┘   └──────┘   └───────┘   └──────────┘
│       │          │                                                    │
│       │ 开机     │ 最多5轮，静默超                                    │
│       │ 打招呼   │ 时75s或第5轮后                                     │
│       │          │ 自动推进                                           │
│       └──────────┘                                                    │
│                                                                       │
│  BOOT ─── 播放预合成开场白                                            │
│  CHAT ─── VAD 免手录音 → STT → LLM → TTS（每轮计数）                 │
│  TRANSITION ─ 过渡话术 → 准备放松                                     │
│  AUDIO ─── 循环播放白噪音/轻音乐/冥想音频，最长45分钟                 │
│  SLEEP ─── 短暂停留5秒，确认入眠                                      │
│  SHUTDOWN ─ 开发期打日志 / 生产期执行 sudo halt                       │
│                                                                       │
│  ⚠ 单向不可逆：不支持回退，用户说"再聊会"也不返回 CHAT               │
└─────────────────────────────────────────────────────────────────────┘
```

### 特殊路径

```
CHAT 内部细节：

  ┌─ start ─────────────────────────────────────────────┐
  │                                                     │
  │  record_vad_with_timeout(timeout=75s)               │
  │       │                                              │
  │       ├── [超时无人说话] → 播放 soft_close → TRANSITION
  │       │                                              │
  │       └── [检测到语音]                               │
  │              │                                       │
  │              ▼                                       │
  │         STT 转写                                     │
  │              │                                       │
  │         ┌────┴────┐                                  │
  │         │ 失败     │                                  │
  │         │ 重试1次  │                                  │
  │         └────┬────┘                                  │
  │         ┌────┴────┐                                  │
  │         │ 仍失败   │──→ 提示"我没听清" → 回到监听    │
  │         └─────────┘   （不占轮次）                    │
  │              │                                       │
  │              ▼                                       │
  │         LLM 回复（带轮次 system prompt）              │
  │              │                                       │
  │              ▼                                       │
  │         TTS 播放回复                                  │
  │              │                                       │
  │         chat_round += 1                              │
  │              │                                       │
  │         ┌────┴────┐                                  │
  │         │ <5轮     │──→ 回到录音继续监听              │
  │         │ =第5轮   │──→ 播放 round5_close → TRANSITION│
  │         └─────────┘                                  │
  └─────────────────────────────────────────────────────┘
```

## 三、SleepFlow 类

### `SleepFlow.__init__(config, gui=None)`

初始化状态机。接收配置字典和可选的 BotGUI 实例。

| 参数 | 类型 | 说明 |
|------|------|------|
| `config` | `dict` | 配置字典（建议传入 `CURRENT_CONFIG`） |
| `gui` | `BotGUI` 或 `None` | BotGUI 实例。提供 `speak()`、`transcribe_audio()`、`set_state()`、`play_sound()`、`_render()` 等方法。为 `None` 时进入纯日志模式（无音频 I/O） |

初始化时自动完成：
1. 读取 `sleep_flow` 配置段
2. 创建缓存目录 (`cache/`)
3. 逐条预合成固定话术（开场白、过渡语、收尾句）并落盘

### `SleepFlow.start()`

**阻塞**运行状态机主循环，直到进入 `SHUTDOWN` 状态。主循环结构：

```python
while self.state != SleepState.SHUTDOWN:
    if self.state == BOOT:       _run_boot()
    elif self.state == CHAT:     _run_chat()
    elif self.state == TRANSITION: _run_transition()
    elif self.state == AUDIO:    _run_audio()
    elif self.state == SLEEP:    _run_sleep()
```

任何状态内抛出未捕获异常 → `_force_next()` 强制推进到下一状态，**不会**导致整个进程崩溃。

### `SleepFlow.stop()`

线程安全的停止方法。设置 `_exit_flag`，状态机在下一个检测点退出。

### `SleepFlow._transition_to(new_state)`

状态转移统一入口：打印 `[FLOW] prev -> next` 日志，修改 `self.state`。未来可在此处加入状态变更回调/埋点。

### `SleepFlow._force_next()`

异常紧急推进。按 `SleepState` 枚举顺序跳到下一个状态；已在最后一个状态则跳到 `SHUTDOWN`。

## 四、各状态详解

### 4.1 BOOT — 开机问候

- 调用 `gui.set_state("greeting", "晚上好")` 更新表情动画
- 播放预合成开场白（key: `greeting`）
- 自动转入 `CHAT`，`chat_round` 置 0

### 4.2 CHAT — 倾听与对话

核心对话状态，控制逻辑如下：

| 配置项 | 默认值 | 作用 |
|--------|--------|------|
| `max_chat_rounds` | 5 | 最大对话轮次，第 5 轮强制过渡 |
| `silence_timeout_chat` | 75 (秒) | 用户安静超过此秒数 → 自动软收尾 |

**每轮流程**：

1. **录音**：调用 `record_vad_with_timeout(timeout=silence_timeout)`（详见第五节）
2. **超时分支**：返回 `None` → 播放 `soft_close` → 跳 `TRANSITION`
3. **STT**：通过 `gui.transcribe_audio()` 转写
   - 失败：重试 1 次，仍失败则 TTS 提示"我没听清"并继续监听（不占轮次）
4. **LLM**：用 `get_chat_prompt(round_num, max_rounds)` 构造 system prompt，调用 `ollama.chat`
   - 超时/失败：使用随机 fallback 回复
5. **TTS**：通过 `gui.speak(reply)` 播放回复
6. **计数**：`chat_round += 1`，达 `max_rounds` 时播放 `round5_close` 并跳 `TRANSITION`

### 4.3 TRANSITION — 过渡

- 播放预合成过渡话术（key: `transition`）
- 直接转入 `AUDIO`

### 4.4 AUDIO — 放松音频播放

| 配置项 | 默认值 | 作用 |
|--------|--------|------|
| `audio_type` | `"white_noise"` | 音频类型，可选 `white_noise` / `light_music` / `meditation` |
| `shutdown_timeout` | 2700 (45分钟) | 音频最长播放时长 |

播放逻辑：
1. 检查 `sounds/relax/<audio_type>.wav` 是否存在
2. 存在 → 循环播放该文件直到超时
3. 不存在 → 用 `scipy` 生成白噪音音频并实时播放
4. 超时后自动转入 `SLEEP`

### 4.5 SLEEP — 确认入眠

- 静态等待 5 秒
- 转入 `SHUTDOWN`

### 4.6 SHUTDOWN — 关机

| 配置项 | 默认值 | 作用 |
|--------|--------|------|
| `shutdown_enabled` | `false` | `true` = 执行 `sudo halt`；`false` = 仅打印日志 |

无论开关闭，最后都会调用 `gui.safe_exit()` 安全退出 GUI。

## 五、record_vad_with_timeout() — 带超时的 VAD 录音

独立于 `BotGUI.record_voice_vad()` 的录音函数，**关键区别是新增 `timeout` 和 `exit_flag` 参数**。

```python
record_vad_with_timeout(
    timeout=75,          # 等待人声起始的最大秒数；None = 一直等
    config=CURRENT_CONFIG,
    exit_flag=None,      # threading.Event，置位时立即退出
) -> str | None          # wav 路径，或 None（超时/退出/错误）
```

**状态机**：

```
WAITING ──→ 连续人声达 vad_start_ms ──→ RECORDING
  │                                            │
  │ 超时 / exit_flag_set                        │ 尾部静音达 vad_silence_ms
  │                                            │ 或达 vad_max_record_ms
  ▼                                            ▼
None                                        wav 文件路径
```

**配置项**（复用 `config.json` 顶层 VAD 参数）：

| 键 | 说明 |
|----|------|
| `vad_aggressiveness` | webrtcvad 灵敏度 0~3 |
| `vad_start_ms` | 判定"开始说话"的连续人声时长 |
| `vad_silence_ms` | 判定"说完"的尾部静音时长 |
| `vad_max_record_ms` | 单次最长录音 |
| `vad_preroll_ms` | 起始前回看缓冲，防吞字 |

## 六、预合成缓存机制

### 目的

- 开机白（BOOT）、过渡句（TRANSITION）、软收尾句等固定话术提前合成为 WAV 文件
- 运行时直接播放文件，避免每次开机都重新合成（节省树莓派 CPU）

### 流程

```
__init__ 时:
  for each key in pre_synthesize_texts:
    cache/<key>.wav 是否存在?
      ├── 是 → 跳过（命中缓存）
      └── 否 → 调用 gui._render(text) 合成 → _save_float32_wav() 落盘
               如果 _render 不可用或失败 → 跳过缓存，运行时实时 TTS

运行时:
  _play_cached(key) 时:
    cache/<key>.wav 是否存在?
      ├── 是 → gui.play_sound(path) 直接播放
      └── 否 → gui.speak(fallback_text) 实时合成
```

### 缓存目录

- 默认 `cache/`（由 `sleep_flow.cache_dir` 控制）
- 已在 `.gitignore` 中忽略
- 文件名：`{key}.wav`，key 对应 `pre_synthesize_texts` 字典的键

### 更新缓存

删除 `cache/` 目录下对应 WAV 文件后重启程序即可重新生成。

## 七、与现有模块的集成

### 依赖关系图

```
flow.py
  ├── 依赖: config.py (CURRENT_CONFIG, OLLAMA_OPTIONS, TEXT_MODEL, VAD函数)
  ├── 依赖: prompts.py (SYSTEM_PROMPT, get_chat_prompt)
  ├── 可选: BotGUI (gui 参数, 提供 TTS/STT/GUI 方法)
  ├── 直接: ollama (LLM 调用)
  ├── 直接: sounddevice / webrtcvad / numpy (录音与音频播放)
  └── 不依赖: agent.py（不修改 agent.py 任何代码）
```

### prompts.py 新增内容

```python
from prompts import (
    SYSTEM_PROMPT,                    # 原有的系统提示词
    get_chat_prompt(round, max),     # 带轮次信息的 chat prompt
    get_transition_prompt(),         # 过渡 prompt（预留）
    get_boot_prompt(),               # 开机 prompt（预留）
)
```

`get_chat_prompt()` 内部根据轮次自动追加收尾引导：

| 轮次 | 追加内容 |
|------|----------|
| 前几轮 | 仅标注 `(当前第 X/Y 轮)` |
| 倒数第 2 轮 + `对话接近尾声，可以开始引导用户放松了` |
| 最后一轮 | `这是本轮最后一次交流，请自然收尾，告诉用户准备放松休息` |

### config.json 新增配置段

```json
"sleep_flow": {
    "max_chat_rounds": 5,           // CHAT 状态最大对话轮次
    "silence_timeout_chat": 75,     // CHAT 安静超时秒数
    "audio_type": "white_noise",    // 放松音频类型
    "audio_types": ["white_noise", "light_music", "meditation"],  // 可选类型列表（用于切换）
    "shutdown_timeout": 2700,       // 音频播放时长（秒），2700 = 45分钟
    "shutdown_enabled": false,      // 是否真关机（开发期设为 false）
    "cache_dir": "cache",           // 预合成缓存目录
    "pre_synthesize_texts": {       // 固定话术列表
        "greeting":     "晚上好，今天过得怎么样？有什么想说的吗？",
        "transition":   "好的，已经记下了。现在让我们慢慢放松，准备休息吧。",
        "soft_close":   "如果你没什么想说的了，我们就开始放松吧。",
        "round5_close": "我们先到这里，准备休息吧。"
    }
}
```

### main.py 使用示例

将原来的开放式问答循环替换为 SleepFlow，`agent.py` 不动：

```python
# main.py — 睡前情绪梳理机器人入口
from config import CURRENT_CONFIG
from agent import BotGUI

def main():
    root = tk.Tk()
    app = BotGUI(root)
    
    # 创建状态机并运行（接管主逻辑线程）
    from flow import SleepFlow
    flow = SleepFlow(config=CURRENT_CONFIG, gui=app)
    
    # 启动状态机（在单独线程中运行，避免阻塞 Tk 主循环）
    import threading
    threading.Thread(target=flow.start, daemon=True).start()
    
    root.mainloop()

if __name__ == "__main__":
    main()
```

要点：
- `SleepFlow` 接管 `BotGUI` 的 TTS/STT/状态显示，不再需要 `safe_main_execution`
- `BotGUI` 的 `speak()`、`transcribe_audio()`、`set_state()` 等方法被 `SleepFlow` 调用
- `root.mainloop()` 仍在主线程，GUI 保持响应

## 八、错误处理策略

| 故障点 | 处理方式 |
|--------|----------|
| **STT 首次失败** | 静默重试 1 次 |
| **STT 二次失败** | TTS 提示"我没听清，可以再说一遍吗"，继续监听（不占轮次） |
| **TTS 合成失败** | 跳过缓存，运行时实时合成；实时合成也失败时仅打印错误 |
| **LLM 超时/报错** | 使用随机 fallback 回复（`["嗯，我在听。", "好的，我知道了。", ...]`） |
| **音频播放异常** | 用 `time.sleep` 等待剩余时间，不崩溃 |
| **状态内未捕获异常** | `_force_next()` 强制推进到下一状态，打印完整 traceback |
| **录音设备不可用** | `record_vad_with_timeout` 返回 `None`，走超时分支 |
| **缓存文件损坏** | 删除后自动重新生成 |

## 九、开发期与生产期行为

| 行为 | 开发期 (`shutdown_enabled=false`) | 生产期 (`shutdown_enabled=true`) |
|------|----------------------------------|----------------------------------|
| SHUTDOWN 动作 | 打印 `[SHUTDOWN]` 日志 | 执行 `sudo halt` |
| 录音 | 实际录音（可听） | 同左 |
| TTS | 实际播放 | 同左 |
| 放松音频 | 实际播放 | 同左 |
| 缓存 | 写入 `cache/` | 同左 |
| 开机 | 流程完整运行 | 同左 |

## 十、关键变量速查

| 变量 | 类型 | 位置 | 说明 |
|------|------|------|------|
| `self.state` | `SleepState` | `flow.py` | 当前状态枚举 |
| `self.chat_round` | `int` | `flow.py` | CHAT 阶段已完成的轮次（0~4） |
| `self._exit_flag` | `bool` | `flow.py` | 外部停止请求标志（`stop()` 方法设置） |
| `self.cache_dir` | `str` | `flow.py` | 预合成缓存目录路径 |
| `self.sleep_cfg` | `dict` | `flow.py` | `config["sleep_flow"]` 的快捷引用 |
| `self.gui` | `BotGUI` | `flow.py` | 可选的 GUI 实例引用 |

## 十一、文件清单（档2 新增/修改）

| 文件 | 操作 | 说明 |
|------|------|------|
| `flow.py` | **新增** | 状态机编排，~420 行 |
| `flow.md` | **新增** | 本文档 |
| `prompts.py` | 修改 | 新增 `get_chat_prompt()` 等 3 个函数 |
| `config.json` | 修改 | 新增 `sleep_flow` 配置段 |
| `.gitignore` | 修改 | 新增 `cache/` 忽略规则 |
| `main.py` | 参考 | 替换为主循环调用 `SleepFlow` |
