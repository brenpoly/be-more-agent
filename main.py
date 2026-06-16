# =========================================================================
#  Be More Agent · 睡前情绪梳理机器人入口
#  用 SleepFlow 状态机替换原有的开放式问答主循环。
#
#  依赖: agent.py (BotGUI), flow.py (SleepFlow), config.py, prompts.py
#
#  启动方式: python main.py
#  注: 保留 agent.py 不动，agent.py 的 if __name__ == "__main__" 在新流程中不再使用。
# =========================================================================

import tkinter as tk
import threading

from config import CURRENT_CONFIG
from agent import BotGUI


def main():
    print("--- 睡前情绪梳理机器人 STARTING ---", flush=True)

    # 1. 创建 Tk 窗口和 GUI
    root = tk.Tk()
    app = BotGUI(root)

    # 2. 创建 SleepFlow 状态机，传入 BotGUI 实例
    #    SleepFlow 会自动接管对话循环，不需要 BotGUI.safe_main_execution
    from flow import SleepFlow
    flow = SleepFlow(config=CURRENT_CONFIG, gui=app)

    # 3. 在后台线程启动状态机（不阻塞 Tk 主循环）
    threading.Thread(target=flow.start, daemon=True).start()

    # 4. Tk 主循环在前台运行（响应用户按键等）
    root.mainloop()


# =========================================================================
# 修改说明
#
# 原 entry point (agent.py 末尾):
#   if __name__ == "__main__":
#       root = tk.Tk()
#       app = BotGUI(root)
#       root.mainloop()
#
# 改为:
#   python main.py   ← SleepFlow 状态机自动接管
#
# 关键变化:
#   1. BotGUI 不再启动 safe_main_execution 线程
#   2. SleepFlow 代替 safe_main_execution 控制交互流程
#   3. BotGUI 的 set_state / speak / transcribe_audio 等方法被 SleepFlow 调用
#   4. 原有唤醒词 / PTT / 开放式对话全部停用
#   5. agent.py 本身不做任何修改
# =========================================================================

if __name__ == "__main__":
    main()
