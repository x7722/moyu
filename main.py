# -*- coding: utf-8 -*-
"""
魔芋 - 防偷窥小工具

主入口：根据环境选择 GUI 或无界面模式运行。
支持首次运行配置向导。
"""

import os

from core.config_loader import load_config
from core.deps import tk
from core.paths import get_base_dir


def get_user_config_path() -> str:
    """获取用户配置文件路径"""
    return os.path.join(get_base_dir(), "user_config.yml")


def check_first_run() -> bool:
    """检查是否首次运行（用户配置文件不存在）"""
    return not os.path.exists(get_user_config_path())


def run_setup_wizard() -> bool:
    """运行配置向导，返回是否完成配置"""
    if tk is None:
        return False

    try:
        from ui.setup_wizard import SetupWizard, save_user_config

        def on_complete(config):
            config_path = get_user_config_path()
            save_user_config(config, config_path)
            print(f"配置已保存到: {config_path}")

        wizard = SetupWizard(on_complete=on_complete)
        return wizard.run()
    except Exception as e:
        print(f"配置向导启动失败: {e}")
        return False


def main():
    """程序入口：加载配置后启动检测。"""
    try:
        # 检查是否首次运行
        if check_first_run() and tk is not None:
            print("首次运行，启动配置向导...")
            if not run_setup_wizard():
                print("配置向导已跳过，使用默认配置")

        # 加载配置
        print("正在加载配置...")
        config = load_config()

        # 优先尝试 GUI 模式
        if tk is not None:
            try:
                print("正在初始化摄像头...")
                from ui.ui_app import CameraPreviewApp
                
                print("正在启动界面...")
                app = CameraPreviewApp(config)
                app.run()
                return
            except Exception as e:
                print(f"GUI 模式启动失败: {e}")
                import traceback
                traceback.print_exc()

        # 回退到无界面模式
        from ui.headless import run_headless
        run_headless(config)
    except Exception as e:
        print(f"程序错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


