# -*- coding: utf-8 -*-
"""
moyu - 防偷窥小工具

主入口：根据环境选择 GUI 或无界面模式运行。
"""

from core.config_loader import load_config
from core.deps import tk


def main():
    """程序入口：加载配置后启动检测。"""
    config = load_config()

    # 优先尝试 GUI 模式
    if tk is not None:
        try:
            from ui.ui_app import CameraPreviewApp
            app = CameraPreviewApp(config)
            app.run()
            return
        except Exception as e:
            print(f"GUI 模式启动失败: {e}")

    # 回退到无界面模式
    from ui.headless import run_headless
    run_headless(config)


if __name__ == "__main__":
    main()
