# =========================================================================
#  Be More Agent · 睡前情绪梳理状态机
#  档2: 单向状态机编排，从 BOOT 到 SHUTDOWN 共 6 个状态。
#  依赖 config / prompts，与 BotGUI 实例协作完成语音交互。
# =========================================================================

import os
import time
import wave
import random
import traceback
import collections
from enum import Enum

import numpy as np

# 硬件相关库（在无音频硬件的环境缺失时可正常导入 flow.py）
try:
    import sounddevice as sd
    _HAS_SOUNDDEVICE = True
except ImportError:
    sd = None
    _HAS_SOUNDDEVICE = False

try:
    import webrtcvad
    _HAS_WEBRTCVAD = True
except ImportError:
    webrtcvad = None
    _HAS_WEBRTCVAD = False

try:
    import ollama
    _HAS_OLLAMA = True
except ImportError:
    ollama = None
    _HAS_OLLAMA = False

try:
    from config import (
        CURRENT_CONFIG, OLLAMA_OPTIONS, TEXT_MODEL,
        choose_input_samplerate, INPUT_DEVICE_NAME, timed_block,
    )
    from prompts import SYSTEM_PROMPT, get_chat_prompt
    _HAS_CONFIG = True
except (ImportError, ModuleNotFoundError) as e:
    # 在无硬件依赖的开发环境中，config.py 可能因 import sounddevice 失败
    print(f"[FLOW] config.py import 失败: {e}", flush=True)
    print("[FLOW] 使用内置默认配置（纯日志模式）", flush=True)

    # 提供最小化 fallback 常量
    CURRENT_CONFIG = {}
    OLLAMA_OPTIONS = {}
    TEXT_MODEL = ""
    INPUT_DEVICE_NAME = None

    def choose_input_samplerate(device, preferred=None):
        return 16000

    def timed_block(label):
        import contextlib
        @contextlib.contextmanager
        def _inner():
            yield
        return _inner()

    SYSTEM_PROMPT = "你是睡前陪伴机器人，帮助用户在睡前梳理情绪。说话温和、简短。"
    get_chat_prompt = None  # type: ignore

    _HAS_CONFIG = False


# =========================================================================
# 1. STATE ENUM
# =========================================================================

class SleepState(Enum):
    """睡前情绪梳理机器人状态枚举，严格单向转移，不可逆"""
    BOOT       = "boot"
    CHAT       = "chat"
    TRANSITION = "transition"
    AUDIO      = "audio"
    SLEEP      = "sleep"
    SHUTDOWN   = "shutdown"


# =========================================================================
# 2. VAD 录音（带超时）
#  与 BotGUI.record_voice_vad 同源，额外支持 idle-timeout。
# =========================================================================

def check_hardware():
    """检查硬件/软件依赖是否可用，缺失时打印警告"""
    if not _HAS_SOUNDDEVICE:
        print("[HARDWARE] sounddevice 未安装，录音/播放功能不可用", flush=True)
    if not _HAS_WEBRTCVAD:
        print("[HARDWARE] webrtcvad 未安装，VAD 录音功能不可用", flush=True)
    if not _HAS_OLLAMA:
        print("[HARDWARE] ollama 未安装，LLM 对话功能不可用", flush=True)


def record_vad_with_timeout(timeout=None, config=None, exit_flag=None):
    """
    基于 webrtcvad 的免手录音，支持"安静等待"超时。

    行为：
    - 在检测到人声起始前持续监听；超过 timeout 秒无人说话则返回 None
    - 检测到人声后自动录音，直到尾部静音或达 max_record_ms，返回 wav 路径
    - timeout=None 时不会因安静而超时（即原版行为）

    Args:
        timeout:         等待人声起始的超时秒数（对录音阶段不生效）
        config:          配置字典（默认 CURRENT_CONFIG）
        exit_flag:       可选 threading.Event，置位时提前退出返回 None

    Returns:
        str: 录音文件路径，或 None（超时 / 错误 / 退出标志）
    """
    if not _HAS_SOUNDDEVICE or not _HAS_WEBRTCVAD:
        print("[VAD] 硬件依赖缺失，无法录音", flush=True)
        return None

    if config is None:
        config = CURRENT_CONFIG

    VAD_RATE = 16000
    FRAME_MS = 30
    frame_samples = int(VAD_RATE * FRAME_MS / 1000)  # 480 samples @ 16kHz

    aggressiveness = int(config.get("vad_aggressiveness", 2))
    start_frames   = max(1, int(config.get("vad_start_ms", 150)   / FRAME_MS))
    silence_frames = max(1, int(config.get("vad_silence_ms", 900) / FRAME_MS))
    max_frames     = max(1, int(config.get("vad_max_record_ms", 30000) / FRAME_MS))
    preroll_frames = max(0, int(config.get("vad_preroll_ms", 300) / FRAME_MS))
    skip_frames    = int(200 / FRAME_MS)  # 丢弃头部 ~200ms，避开上一句 TTS 的回声尾巴

    vad = webrtcvad.Vad(aggressiveness)

    # 采样率协商
    input_rate = choose_input_samplerate(INPUT_DEVICE_NAME, VAD_RATE)
    use_resampling = (input_rate != VAD_RATE)
    read_size = int(input_rate * FRAME_MS / 1000) if use_resampling else frame_samples

    buffer = []                                          # 已确认录音的帧（int16, 16000Hz）
    preroll = collections.deque(maxlen=preroll_frames)   # 起始前回看缓冲
    recording = False
    voiced_run = 0
    silence_run = 0
    total_frames = 0
    idle_start = time.time()

    filename = f"flow_input_{int(time.time())}.wav"

    try:
        # 释放硬件，避免 Pi 上音频争用死锁
        sd.stop()
        time.sleep(0.2)

        with sd.InputStream(samplerate=input_rate, channels=1, dtype='int16',
                            blocksize=read_size, device=INPUT_DEVICE_NAME) as stream:
            while True:
                # --- 外部退出标志检查 ---
                if exit_flag is not None and exit_flag.is_set():
                    print("[VAD] Exit flag set, stopping.", flush=True)
                    return None

                # --- 空闲超时检测（仅等待说话阶段）---
                if not recording and timeout is not None:
                    elapsed = time.time() - idle_start
                    if elapsed > timeout:
                        print(f"[VAD TIMEOUT] No speech for {elapsed:.1f}s", flush=True)
                        return None

                data, _overflow = stream.read(read_size)
                frame = np.frombuffer(data, dtype=np.int16)
                if frame.ndim > 1:
                    frame = frame.flatten()

                # 最近邻重采样到 480 样本/帧（如果设备不支持 16kHz 直采）
                if use_resampling:
                    step = len(frame) / frame_samples
                    idx = np.arange(0, len(frame), step)[:frame_samples].astype(int)
                    frame = frame[idx]
                if len(frame) != frame_samples:
                    continue

                # 丢弃头部帧，避开上一句 TTS 的房间回声尾巴
                if skip_frames > 0:
                    skip_frames -= 1
                    continue

                is_speech = vad.is_speech(frame.tobytes(), VAD_RATE)

                if not recording:
                    preroll.append(frame.copy())
                    if is_speech:
                        voiced_run += 1
                        if voiced_run >= start_frames:
                            recording = True
                            # 预缓冲并入开头，避免吞掉第一个字
                            buffer.extend(preroll)
                            preroll.clear()
                            total_frames = len(buffer)
                            silence_run = 0
                            print("[VAD] Speech detected, recording...", flush=True)
                    else:
                        voiced_run = 0
                else:
                    buffer.append(frame.copy())
                    total_frames += 1
                    if is_speech:
                        silence_run = 0
                    else:
                        silence_run += 1
                        if silence_run >= silence_frames:
                            print("[VAD] Trailing silence, stop.", flush=True)
                            break
                    if total_frames >= max_frames:
                        print("[VAD] Max record time reached, stop.", flush=True)
                        break
    except Exception as e:
        print(f"[VAD ERROR] Recording failed: {e}", flush=True)
        return None

    if not buffer:
        return None
    return _save_int16_buffer(buffer, filename, samplerate=VAD_RATE)


def _save_int16_buffer(buffer, filename, samplerate=16000):
    """将 int16 音频帧列表保存为 wav 文件"""
    try:
        audio_data = np.concatenate(buffer, axis=0).flatten().astype(np.int16)
        with wave.open(filename, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(samplerate)
            wf.writeframes(audio_data.tobytes())
        return filename
    except Exception as e:
        print(f"[AUDIO] Save buffer error: {e}", flush=True)
        return None


# =========================================================================
# 3. 放松音频生成
# =========================================================================

def _generate_white_noise(duration_sec, sample_rate=44100):
    """生成白噪音音频 (samples, rate)"""
    n = int(sample_rate * duration_sec)
    noise = np.random.randn(n).astype(np.float32) * 0.3
    return noise, sample_rate


# =========================================================================
# 4. SLEEP FLOW 状态机
# =========================================================================

class SleepFlow:
    """
    睡前情绪梳理机器人状态机编排。

    单向状态转移（不可逆）::

        BOOT → CHAT → TRANSITION → AUDIO → SLEEP → SHUTDOWN

    使用方式::

        flow = SleepFlow(config=CURRENT_CONFIG, gui=bot_gui)
        flow.start()          # 阻塞直到 SHUTDOWN

    参数:
        config:  配置字典（通常是 ``CURRENT_CONFIG``）
        gui:     BotGUI 实例（提供 speak / transcribe_audio / set_state / play_sound 等方法）
                 为 None 时进入纯日志模式（无音频 I/O），适合调试。
    """

    # --- LLM 回复 fallback 池 ------------------------------------------------
    FALLBACKS = [
        "嗯，我在听。",
        "好的，我知道了。",
        "放松一点，没事的。",
        "我在听你说。",
    ]

    def __init__(self, config, gui=None):
        self.cfg = config
        self.sleep_cfg = config.get("sleep_flow", {})
        self.gui = gui

        # --- 硬件检查 ---
        check_hardware()

        # --- 状态 ---
        self.state = SleepState.BOOT
        self.chat_round = 0
        self._exit_flag = False

        # --- 预合成缓存目录 ----------------------------------------------------
        self.cache_dir = self.sleep_cfg.get("cache_dir", "cache")
        os.makedirs(self.cache_dir, exist_ok=True)

        # --- 预合成固定话术 ---
        self._presynth_all()

        print(f"[FLOW] SleepFlow initialized  |  cache={os.path.abspath(self.cache_dir)}", flush=True)

    # =========================================================================
    # 4a.  缓存管理
    # =========================================================================

    def _cache_path(self, key):
        """返回缓存 wav 的完整路径"""
        return os.path.join(self.cache_dir, f"{key}.wav")

    def _presynth_all(self):
        """遍历 pre_synthesize_texts，缺失的调用 gui._render 补全并落盘"""
        texts = self.sleep_cfg.get("pre_synthesize_texts", {})
        if not texts:
            return

        renderer = None
        if self.gui and hasattr(self.gui, "_render"):
            renderer = self.gui._render

        for key, text in texts.items():
            path = self._cache_path(key)
            if os.path.exists(path):
                print(f"[CACHE] Hit: {key}", flush=True)
                continue

            print(f"[CACHE] Synthesizing: {key} ...", flush=True)
            try:
                if renderer is not None:
                    result = renderer(text)
                    if result is not None:
                        samples, rate = result
                        _save_float32_wav(samples, rate, path)
                        print(f"[CACHE] Saved: {key} -> {path}", flush=True)
                        continue
                # 没有 renderer 或渲染失败 → 跳过缓存，运行时走实时 TTS
                print(f"[CACHE] Skip (no renderer): {key}", flush=True)
            except Exception as e:
                print(f"[CACHE] Error synthesizing {key}: {e}", flush=True)

    def _play_cached(self, key, fallback_text=None):
        """
        播放缓存 wav；不存在则用 gui.speak(fallback_text) 实时合成。
        返回 True 表示实际播放/说了一句话。
        """
        path = self._cache_path(key)
        if os.path.exists(path) and self.gui:
            print(f"[AUDIO] Playing cached: {key}", flush=True)
            self.gui.play_sound(path)
            return True

        # 缓存缺失 → 实时 TTS
        if fallback_text is None:
            texts = self.sleep_cfg.get("pre_synthesize_texts", {})
            fallback_text = texts.get(key, "")
        if fallback_text and self.gui:
            print(f"[AUDIO] Live TTS: {key}", flush=True)
            self.gui.speak(fallback_text)
            return True

        return False

    # =========================================================================
    # 4b.  GUI / 日志辅助
    # =========================================================================

    def _set_state(self, state_name, msg=""):
        """更新 GUI 状态显示；无 GUI 时仅打印日志"""
        if self.gui:
            self.gui.set_state(state_name, msg)
        print(f"[FLOW] [{self.state.value}] {msg}", flush=True)

    def _append_text(self, text):
        """追加文字到 GUI 对话文本框"""
        if self.gui:
            self.gui.append_to_text(text)

    # =========================================================================
    # 4c.  LLM 调用
    # =========================================================================

    def _call_llm(self, user_text, system_override=None):
        """
        调用本地 Ollama LLM，返回回复文本；失败时返回随机 fallback。

        Args:
            user_text:        本轮用户语音转写文本
            system_override:  可选的 system prompt 覆盖（默认用 SYSTEM_PROMPT）
        """
        system = system_override or SYSTEM_PROMPT
        lang = self.cfg.get("whisper_lang", "zh")
        lang_hint = "请用中文回答。" if lang == "zh" else ""

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_text + ("\n" + lang_hint if lang_hint else "")},
        ]

        try:
            with timed_block(f"LLM chat (round {self.chat_round})"):
                resp = ollama.chat(
                    model=TEXT_MODEL,
                    messages=messages,
                    stream=False,
                    options=OLLAMA_OPTIONS,
                    keep_alive=-1,
                )
            return _extract_ollama_content(resp)
        except Exception as e:
            print(f"[LLM ERROR] {e}", flush=True)
            traceback.print_exc()

        # LLM 超时/失败 → fallback
        return random.choice(self.FALLBACKS)

    # =========================================================================
    # 4d.  STT 转写
    # =========================================================================

    def _transcribe(self, audio_file):
        """
        转写音频文件，失败时重试一次。

        Returns:
            str:  转写文本（去两端空白），或 None（两次均失败）
        """
        if not audio_file or not os.path.exists(audio_file):
            return None

        text = self._transcribe_once(audio_file)
        if text:
            return text

        print("[STT] First attempt failed, retrying once...", flush=True)
        time.sleep(0.5)
        text = self._transcribe_once(audio_file)
        if text:
            return text

        # 二次失败 → 提示用户重说
        print("[STT] Both attempts failed, prompting user...", flush=True)
        if self.gui:
            self.gui.speak("我没听清，可以再说一遍吗")
        return None

    def _transcribe_once(self, audio_file):
        """单次转写，失败返回空字符串"""
        try:
            if self.gui:
                text = self.gui.transcribe_audio(audio_file) or ""
            else:
                text = ""
            if text.strip():
                return text.strip()
        except Exception as e:
            print(f"[STT ERROR] {e}", flush=True)
        return ""

    # =========================================================================
    # 4e.  放松音频播放
    # =========================================================================

    def _play_relax_audio(self, audio_type, timeout):
        """
        播放放松音频（白噪音/轻音乐/冥想），持续 timeout 秒或音频放完。

        优先从 ``sounds/relax/<type>.wav`` 循环播放；
        文件不存在则生成白噪音。
        """
        audio_path = os.path.join("sounds", "relax", f"{audio_type}.wav")
        start = time.time()

        if os.path.exists(audio_path) and self.gui:
            print(f"[AUDIO] Playing file: {audio_path}", flush=True)
            while time.time() - start < timeout and not self._exit_flag:
                self.gui.play_sound(audio_path)
            return

        # 无文件 → 生成白噪音
        if not _HAS_SOUNDDEVICE:
            print(f"[AUDIO] sounddevice 不可用，无法播放音频，静等超时", flush=True)
            time.sleep(min(timeout, 10))
            return
        print(f"[AUDIO] No file at {audio_path}, generating white noise", flush=True)
        try:
            SAMPLE_RATE = 44100
            # 每次生成最长 5 分钟，循环播放直到超时
            chunk_sec = min(timeout, 300)
            noise, rate = _generate_white_noise(chunk_sec, SAMPLE_RATE)

            while time.time() - start < timeout and not self._exit_flag:
                remaining = timeout - (time.time() - start)
                play_sec = min(remaining, chunk_sec)
                end = int(rate * play_sec)
                sd.play(noise[:end], rate)
                sd.wait()
        except Exception as e:
            print(f"[AUDIO] Playback error: {e}", flush=True)
            # 音频播放失败 → 静等剩余时间
            elapsed = time.time() - start
            remaining = timeout - elapsed
            if remaining > 0:
                time.sleep(min(remaining, 10))

    # =========================================================================
    # 5.  PUBLIC API
    # =========================================================================

    def start(self):
        """
        启动状态机主循环，阻塞直到 SHUTDOWN。

        状态转移: BOOT → CHAT → TRANSITION → AUDIO → SLEEP → SHUTDOWN
        """
        print("=" * 50, flush=True)
        print("  睡前情绪梳理机器人  Sleep Flow", flush=True)
        print("=" * 50, flush=True)

        while self.state != SleepState.SHUTDOWN and not self._exit_flag:
            try:
                if self.state == SleepState.BOOT:
                    self._run_boot()
                elif self.state == SleepState.CHAT:
                    self._run_chat()
                elif self.state == SleepState.TRANSITION:
                    self._run_transition()
                elif self.state == SleepState.AUDIO:
                    self._run_audio()
                elif self.state == SleepState.SLEEP:
                    self._run_sleep()
                else:
                    break
            except Exception as e:
                print(f"[FLOW CRITICAL] 状态 {self.state.value} 异常: {e}", flush=True)
                traceback.print_exc()
                # 出错后强制推进到下一状态，防止卡死
                self._force_next()

        self._run_shutdown()

    def stop(self):
        """安全停止状态机（可在另一线程调用）"""
        self._exit_flag = True

    # =========================================================================
    # 6.  各状态执行方法
    # =========================================================================

    # ------------------------------------------------------------------
    # BOOT
    # ------------------------------------------------------------------

    def _run_boot(self):
        """播放开机问候，自动转入 CHAT"""
        self._set_state("greeting", "晚上好")
        self._play_cached("greeting")
        self._transition_to(SleepState.CHAT)

    # ------------------------------------------------------------------
    # CHAT
    # ------------------------------------------------------------------

    def _run_chat(self):
        """
        多轮对话状态。

        流程::

            录音（VAD + 静默超时）→ STT → LLM → TTS（缓存或实时）
                    ↑ 失败重试1次，仍失败提示后继续下一轮
                    └── 超时无人说话 → 软收尾 → 跳到 TRANSITION

        第 max_chat_rounds 轮播放收尾话术后强制转入 TRANSITION。
        """
        max_rounds = self.sleep_cfg.get("max_chat_rounds", 5)
        silence_timeout = self.sleep_cfg.get("silence_timeout_chat", 75)

        self.chat_round = 0

        while self.chat_round < max_rounds:
            if self._exit_flag:
                return

            round_label = f"第 {self.chat_round+1}/{max_rounds} 轮"
            self._set_state("listening", f"我在听… {round_label}")

            # --- 录音（带安静超时） ---
            audio_file = record_vad_with_timeout(
                timeout=silence_timeout,
                config=self.cfg,
                exit_flag=None,  # 用 self._exit_flag 在外部线程控制
            )

            if self._exit_flag:
                return

            if audio_file is None:
                # 安静超时 → 软收尾后过渡
                print("[CHAT] 安静超时，软收尾...", flush=True)
                self._play_cached("soft_close")
                self._transition_to(SleepState.TRANSITION)
                return

            # --- STT 转写 ---
            user_text = self._transcribe(audio_file)
            if user_text is None:
                # 两次 STT 均失败，提示后继续监听（不占用轮次）
                continue

            # --- 追加对话记录 ---
            self._append_text(f"你: {user_text}")

            # --- 构造带轮次信息的 system prompt ---
            chat_system = get_chat_prompt(self.chat_round, max_rounds)

            # --- LLM 回复 ---
            self._set_state("thinking", "思考中…")
            reply = self._call_llm(user_text, system_override=chat_system)

            if not reply:
                reply = random.choice(self.FALLBACKS)

            # --- TTS 播放 ---
            self._set_state("speaking", "回复中…")
            self._append_text(f"机器人: {reply}")
            if self.gui:
                self.gui.speak(reply)

            # --- 轮次推进 ---
            self.chat_round += 1

            # 已满最大轮次 → 播放收尾话术后过渡
            if self.chat_round >= max_rounds:
                print(f"[CHAT] 达到最大轮次 {max_rounds}，强制过渡", flush=True)
                self._play_cached("round5_close")
                self._transition_to(SleepState.TRANSITION)
                return

        # while 正常结束（理论上不会走到这里，因为 while 条件就是 chat_round < max_rounds）
        if self.state == SleepState.CHAT:
            self._transition_to(SleepState.TRANSITION)

    # ------------------------------------------------------------------
    # TRANSITION
    # ------------------------------------------------------------------

    def _run_transition(self):
        """播放过渡脚本，转入 AUDIO"""
        self._set_state("idle", "准备放松")
        self._play_cached("transition")
        self._transition_to(SleepState.AUDIO)

    # ------------------------------------------------------------------
    # AUDIO
    # ------------------------------------------------------------------

    def _run_audio(self):
        """
        播放放松音频，用户在此阶段入眠。

        - 音频类型由 ``sleep_flow.audio_type`` 指定
        - 持续 ``sleep_flow.shutdown_timeout`` 秒后自动结束
        - 期间不检测用户说话，不打扰
        """
        self._set_state("sleep", "放松中…")
        audio_type = self.sleep_cfg.get("audio_type", "white_noise")
        timeout = self.sleep_cfg.get("shutdown_timeout", 2700)  # 45 分钟

        print(f"[AUDIO] 开始播放: {audio_type}  持续时间: {timeout}s", flush=True)
        self._play_relax_audio(audio_type, timeout)

        self._transition_to(SleepState.SLEEP)

    # ------------------------------------------------------------------
    # SLEEP
    # ------------------------------------------------------------------

    def _run_sleep(self):
        """短暂停留后进入 SHUTDOWN"""
        self._set_state("sleep", "晚安")
        print("[SLEEP] 用户已在放松音频中入眠，5 秒后关机", flush=True)
        time.sleep(5)
        self._transition_to(SleepState.SHUTDOWN)

    # =========================================================================
    # 7.  状态转移 / 关机
    # =========================================================================

    def _transition_to(self, new_state):
        """单向状态转移（打印日志 + 记入内存）"""
        prev = self.state.value
        self.state = new_state
        print(f"[FLOW] {prev} -> {new_state.value}", flush=True)

    def _force_next(self):
        """出错时的紧急推进：无论如何跳到下一个状态"""
        order = list(SleepState)
        try:
            idx = order.index(self.state)
            if idx < len(order) - 1:
                self.state = order[idx + 1]
                print(f"[FLOW] ⚠ 强制前进到 {self.state.value}", flush=True)
            else:
                self.state = SleepState.SHUTDOWN
        except ValueError:
            self.state = SleepState.SHUTDOWN

    def _run_shutdown(self):
        """关机 / 退出"""
        shutdown_enabled = self.sleep_cfg.get("shutdown_enabled", False)

        if shutdown_enabled:
            print("[SHUTDOWN] 执行系统关机...", flush=True)
            self._set_state("sleep", "关机中")
            try:
                import subprocess
                subprocess.run(["sudo", "halt"], check=True, timeout=10)
            except Exception as e:
                print(f"[SHUTDOWN] 关机命令失败: {e}", flush=True)
                print("[SHUTDOWN] 回退: 退出进程", flush=True)
        else:
            print("[SHUTDOWN] 开发模式：此处会执行关机", flush=True)
            print("[SHUTDOWN] 生产环境请设置 shutdown_enabled=true", flush=True)

        # 安全退出 GUI
        if self.gui:
            try:
                self.gui.safe_exit()
            except Exception as e:
                print(f"[SHUTDOWN] safe_exit: {e}", flush=True)

        print("[FLOW] 晚安 🌙", flush=True)


# =========================================================================
# 5. 工具函数
# =========================================================================

def _extract_ollama_content(response):
    """
    从 ollama.chat 响应中安全提取文本内容。
    兼容 ollama 库的 dict-style 与 object-style 两种接口。
    """
    if response is None:
        return ""
    # dict-style
    if isinstance(response, dict):
        return response.get("message", {}).get("content", "")
    # object-style (pydantic BaseModel)
    try:
        return response.message.content
    except AttributeError:
        return ""


def _save_float32_wav(samples, rate, path):
    """将 float32 [-1,1] 音频保存为 16-bit wav 文件"""
    samples_int16 = (samples * 32767).clip(-32768, 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples_int16.tobytes())


# =========================================================================
# 6. 独立测试入口
# =========================================================================

if __name__ == "__main__":
    # 纯日志模式（无 GUI、无音频硬件），验证初始化与状态流转
    print(">>> 测试 SleepFlow 纯日志模式 <<<")
    test_cfg = {
        "text_model": "gemma3:1b",
        "whisper_lang": "zh",
        "sleep_flow": {
            "max_chat_rounds": 2,
            "silence_timeout_chat": 10,
            "audio_type": "white_noise",
            "shutdown_timeout": 30,
            "shutdown_enabled": False,
            "cache_dir": "cache",
            "pre_synthesize_texts": {
                "greeting":    "晚上好，今天过得怎么样？有什么想说的吗？",
                "transition":  "好的，已经记下了。现在让我们慢慢放松，准备休息吧。",
                "soft_close":  "如果你没什么想说的了，我们就开始放松吧。",
                "round5_close":"我们先到这里，准备休息吧。",
            },
        },
    }
    flow = SleepFlow(config=test_cfg, gui=None)
    print(">>> 初始化完成（无异常）<<<")
    print(">>> cache/ 目录已创建，预合成结果如下：")
    for f in sorted(os.listdir(flow.cache_dir)):
        print(f"    {f}")
    print(">>> 测试结束 <<<")
