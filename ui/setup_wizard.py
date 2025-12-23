# -*- coding: utf-8 -*-
"""
首次运行配置向导 - 引导用户完成初始配置。
"""

import os
from typing import Callable, Optional, Dict, Any

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    tk = None
    ttk = None
    filedialog = None
    messagebox = None

try:
    import yaml
except ImportError:
    yaml = None

# 导入 DPI 工具
from .dpi_utils import enable_dpi_awareness, enable_dark_title_bar, scaled_size, extract_app_name


# 现代深色主题配色
class Theme:
    BG_DARK = "#1a1a2e"
    BG_CARD = "#16213e"
    BG_INPUT = "#0f3460"
    PRIMARY = "#4a90d9"
    ACCENT = "#00d4aa"
    TEXT = "#e8e8e8"
    TEXT_SECONDARY = "#888888"
    BORDER = "#2a4a7a"
    ERROR = "#e74c3c"
    SUCCESS = "#2ecc71"


class SetupWizard:
    """首次运行配置向导窗口"""

    def __init__(self, on_complete: Optional[Callable[[Dict[str, Any]], None]] = None):
        if tk is None:
            raise RuntimeError("tkinter 不可用")

        # 启用高 DPI 感知（必须在创建窗口之前调用）
        enable_dpi_awareness()

        self.on_complete = on_complete
        self.config_data: Dict[str, Any] = {
            "work_app": {
                "active": "idea",
                "targets": {}
            },
            "snapshot": {
                "enabled": True,
                "directory": ""
            }
        }
        self.completed = False
        self._setup_ui()

    def _setup_ui(self):
        """构建向导 UI"""
        self.root = tk.Tk()
        self.root.title("魔芋 配置向导")
        self.root.configure(bg=Theme.BG_DARK)
        self.root.resizable(False, False)
        
        # 先更新一次以获取正确的 DPI
        self.root.update_idletasks()
        
        # 基础尺寸 (100% DPI 下的尺寸)
        base_width = 550
        base_height = 650
        
        # 根据 DPI 缩放窗口大小
        window_width, window_height = scaled_size(base_width, base_height, self.root)
        
        # 居中显示
        x = (self.root.winfo_screenwidth() - window_width) // 2
        y = (self.root.winfo_screenheight() - window_height) // 2
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")

        # 启用暗色标题栏
        enable_dark_title_bar(self.root)

        # 主容器
        self.main_frame = tk.Frame(self.root, bg=Theme.BG_DARK)
        self.main_frame.pack(fill="both", expand=True, padx=30, pady=20)

        # 标题
        title_label = tk.Label(
            self.main_frame,
            text="🍠 欢迎使用 魔芋",
            font=("Microsoft YaHei", 20, "bold"),
            fg=Theme.TEXT,
            bg=Theme.BG_DARK
        )
        title_label.pack(pady=(0, 5))

        subtitle_label = tk.Label(
            self.main_frame,
            text="让我们完成一些基本配置",
            font=("Microsoft YaHei", 11),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_DARK
        )
        subtitle_label.pack(pady=(0, 20))

        # 配置区域 - 使用卡片布局
        self._create_work_app_section()
        self._create_snapshot_section()

        # 底部按钮
        self._create_buttons()

    def _create_card(self, parent, title: str) -> tk.Frame:
        """创建卡片容器"""
        card = tk.Frame(parent, bg=Theme.BG_CARD, highlightbackground=Theme.BORDER, highlightthickness=1)
        card.pack(fill="x", pady=10)

        # 卡片标题
        title_frame = tk.Frame(card, bg=Theme.BG_CARD)
        title_frame.pack(fill="x", padx=15, pady=(12, 8))

        tk.Label(
            title_frame,
            text=title,
            font=("Microsoft YaHei", 12, "bold"),
            fg=Theme.PRIMARY,
            bg=Theme.BG_CARD
        ).pack(anchor="w")

        # 内容区域
        content = tk.Frame(card, bg=Theme.BG_CARD)
        content.pack(fill="x", padx=15, pady=(0, 15))

        return content

    def _create_work_app_section(self):
        """工作应用配置区域"""
        content = self._create_card(self.main_frame, "📁 工作应用配置")

        # 说明文字
        tk.Label(
            content,
            text="设置检测到人脸时要切换到的应用程序（可以是任何软件）：",
            font=("Microsoft YaHei", 10),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_CARD,
            wraplength=550,
            justify="left"
        ).pack(anchor="w", pady=(0, 10))

        # 快速选择预设
        preset_frame = tk.Frame(content, bg=Theme.BG_CARD)
        preset_frame.pack(fill="x", pady=5)

        tk.Label(
            preset_frame,
            text="快速选择：",
            font=("Microsoft YaHei", 10),
            fg=Theme.TEXT,
            bg=Theme.BG_CARD
        ).pack(side="left")

        # 预设按钮
        for text, app_name, path_func in [
            ("💻 IDEA", "IntelliJ IDEA", self._get_idea_path),
            ("📝 VSCode", "VSCode", self._get_vscode_path),
            ("🌐 浏览器", "浏览器", self._get_browser_path),
            ("📄 WPS", "WPS Office", self._get_wps_path),
        ]:
            btn = tk.Button(
                preset_frame,
                text=text,
                font=("Microsoft YaHei", 9),
                bg=Theme.BG_INPUT,
                fg=Theme.TEXT,
                relief="flat",
                cursor="hand2",
                command=lambda n=app_name, p=path_func: self._apply_preset(n, p())
            )
            btn.pack(side="left", padx=(10, 0), ipadx=8, ipady=2)

        # 应用名称输入
        name_frame = tk.Frame(content, bg=Theme.BG_CARD)
        name_frame.pack(fill="x", pady=(15, 0))

        tk.Label(
            name_frame,
            text="应用名称：",
            font=("Microsoft YaHei", 10),
            fg=Theme.TEXT,
            bg=Theme.BG_CARD
        ).pack(anchor="w")

        self.app_name_var = tk.StringVar(value="IntelliJ IDEA")
        name_input = tk.Entry(
            name_frame,
            textvariable=self.app_name_var,
            font=("Microsoft YaHei", 10),
            bg=Theme.BG_INPUT,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="flat",
            highlightbackground=Theme.BORDER,
            highlightthickness=1
        )
        name_input.pack(fill="x", pady=5, ipady=6)

        # 路径输入
        path_frame = tk.Frame(content, bg=Theme.BG_CARD)
        path_frame.pack(fill="x", pady=(10, 0))

        tk.Label(
            path_frame,
            text="程序路径：",
            font=("Microsoft YaHei", 10),
            fg=Theme.TEXT,
            bg=Theme.BG_CARD
        ).pack(anchor="w")

        input_frame = tk.Frame(path_frame, bg=Theme.BG_CARD)
        input_frame.pack(fill="x", pady=5)

        self.app_path_var = tk.StringVar()
        self.app_path_entry = tk.Entry(
            input_frame,
            textvariable=self.app_path_var,
            font=("Consolas", 10),
            bg=Theme.BG_INPUT,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="flat",
            highlightbackground=Theme.BORDER,
            highlightthickness=1
        )
        self.app_path_entry.pack(side="left", fill="x", expand=True, ipady=6)

        browse_btn = tk.Button(
            input_frame,
            text="浏览...",
            font=("Microsoft YaHei", 9),
            bg=Theme.PRIMARY,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._browse_app_path
        )
        browse_btn.pack(side="left", padx=(10, 0), ipadx=10, ipady=3)

        # 提示标签
        hint_label = tk.Label(
            content,
            text="💡 选择程序后将自动识别应用名称，如有需要可手动修改",
            font=("Microsoft YaHei", 9),
            fg=Theme.TEXT_SECONDARY,
            bg=Theme.BG_CARD
        )
        hint_label.pack(anchor="w", pady=(8, 0))

        # 初始化默认路径
        self._apply_preset("IntelliJ IDEA", self._get_idea_path())

    def _get_idea_path(self) -> str:
        """获取 IDEA 路径"""
        paths = [
            "C:/Program Files/JetBrains/IntelliJ IDEA/bin/idea64.exe",
            "C:/app/developer/apps/IntelliJ IDEA 2025.1/bin/idea64.exe",
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return paths[0]

    def _get_vscode_path(self) -> str:
        """获取 VSCode 路径"""
        paths = [
            f"C:/Users/{os.getlogin()}/AppData/Local/Programs/Microsoft VS Code/Code.exe",
            "C:/Program Files/Microsoft VS Code/Code.exe",
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return "code"

    def _get_browser_path(self) -> str:
        """获取浏览器路径"""
        paths = [
            f"C:/Users/{os.getlogin()}/AppData/Local/Google/Chrome/Application/chrome.exe",
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            f"C:/Users/{os.getlogin()}/AppData/Local/Microsoft/Edge/Application/msedge.exe",
            "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return paths[0]

    def _get_wps_path(self) -> str:
        """获取 WPS 路径"""
        paths = [
            f"C:/Users/{os.getlogin()}/AppData/Local/Kingsoft/WPS Office/ksolaunch.exe",
            "C:/Program Files (x86)/Kingsoft/WPS Office/ksolaunch.exe",
        ]
        for path in paths:
            if os.path.exists(path):
                return path
        return paths[0]

    def _apply_preset(self, name: str, path: str):
        """应用预设"""
        self.app_name_var.set(name)
        self.app_path_var.set(path)

    def _create_snapshot_section(self):
        """截图配置区域"""
        content = self._create_card(self.main_frame, "📷 截图配置")

        # 启用开关
        switch_frame = tk.Frame(content, bg=Theme.BG_CARD)
        switch_frame.pack(fill="x", pady=5)

        self.snapshot_enabled_var = tk.BooleanVar(value=True)
        cb = tk.Checkbutton(
            switch_frame,
            text="启用人脸检测时自动截图",
            variable=self.snapshot_enabled_var,
            font=("Microsoft YaHei", 10),
            fg=Theme.TEXT,
            bg=Theme.BG_CARD,
            selectcolor=Theme.BG_INPUT,
            activebackground=Theme.BG_CARD,
            activeforeground=Theme.TEXT,
            command=self._on_snapshot_toggle
        )
        cb.pack(anchor="w")

        # 存储路径
        self.snapshot_path_frame = tk.Frame(content, bg=Theme.BG_CARD)
        self.snapshot_path_frame.pack(fill="x", pady=(10, 0))

        tk.Label(
            self.snapshot_path_frame,
            text="截图保存位置：",
            font=("Microsoft YaHei", 10),
            fg=Theme.TEXT,
            bg=Theme.BG_CARD
        ).pack(anchor="w")

        input_frame = tk.Frame(self.snapshot_path_frame, bg=Theme.BG_CARD)
        input_frame.pack(fill="x", pady=5)

        # 默认路径
        default_snapshot_dir = os.path.join(os.path.expanduser("~"), "Pictures", "魔芋")
        self.snapshot_path_var = tk.StringVar(value=default_snapshot_dir)

        self.snapshot_path_entry = tk.Entry(
            input_frame,
            textvariable=self.snapshot_path_var,
            font=("Consolas", 10),
            bg=Theme.BG_INPUT,
            fg=Theme.TEXT,
            insertbackground=Theme.TEXT,
            relief="flat",
            highlightbackground=Theme.BORDER,
            highlightthickness=1
        )
        self.snapshot_path_entry.pack(side="left", fill="x", expand=True, ipady=6)

        browse_btn = tk.Button(
            input_frame,
            text="浏览...",
            font=("Microsoft YaHei", 9),
            bg=Theme.PRIMARY,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._browse_snapshot_path
        )
        browse_btn.pack(side="left", padx=(10, 0), ipadx=10, ipady=3)

    def _create_buttons(self):
        """底部按钮"""
        btn_frame = tk.Frame(self.main_frame, bg=Theme.BG_DARK)
        btn_frame.pack(fill="x", pady=(20, 0))

        # 跳过按钮
        skip_btn = tk.Button(
            btn_frame,
            text="跳过",
            font=("Microsoft YaHei", 10),
            bg=Theme.BG_CARD,
            fg=Theme.TEXT_SECONDARY,
            relief="flat",
            cursor="hand2",
            command=self._on_skip
        )
        skip_btn.pack(side="left", ipadx=20, ipady=6)

        # 完成按钮
        complete_btn = tk.Button(
            btn_frame,
            text="保存并开始 ✓",
            font=("Microsoft YaHei", 10, "bold"),
            bg=Theme.ACCENT,
            fg="white",
            relief="flat",
            cursor="hand2",
            command=self._on_complete
        )
        complete_btn.pack(side="right", ipadx=20, ipady=6)


    def _on_snapshot_toggle(self):
        """截图开关变更"""
        enabled = self.snapshot_enabled_var.get()
        state = "normal" if enabled else "disabled"
        for child in self.snapshot_path_frame.winfo_children():
            if isinstance(child, tk.Frame):
                for widget in child.winfo_children():
                    if isinstance(widget, (tk.Entry, tk.Button)):
                        widget.configure(state=state)

    def _browse_app_path(self):
        """浏览应用程序路径，并自动识别应用名称"""
        path = filedialog.askopenfilename(
            title="选择工作应用程序",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")]
        )
        if path:
            self.app_path_var.set(path)
            # 自动识别应用名称
            app_name = extract_app_name(path)
            if app_name:
                self.app_name_var.set(app_name)

    def _browse_snapshot_path(self):
        """浏览截图保存路径"""
        path = filedialog.askdirectory(title="选择截图保存目录")
        if path:
            self.snapshot_path_var.set(path)

    def _on_skip(self):
        """跳过配置"""
        self.completed = False
        self.root.destroy()

    def _on_complete(self):
        """完成配置"""
        # 验证输入
        app_path = self.app_path_var.get().strip()
        if not app_path:
            messagebox.showwarning("提示", "请设置工作应用程序路径")
            return

        snapshot_enabled = self.snapshot_enabled_var.get()
        snapshot_path = self.snapshot_path_var.get().strip()
        if snapshot_enabled and not snapshot_path:
            messagebox.showwarning("提示", "请设置截图保存路径")
            return

        # 构建配置
        app_name = self.app_name_var.get().strip()
        if not app_name:
            app_name = "custom_app"
        
        # 将应用名称转换为安全的 key 名称
        app_key = app_name.lower().replace(" ", "_").replace("/", "_")
        
        # 窗口关键字使用应用名称
        window_keywords = [app_name]

        self.config_data = {
            "work_app": {
                "active": app_key,
                "targets": {
                    app_key: {
                        "windows_command": app_path,
                        "window_keywords": window_keywords,
                        "display_name": app_name
                    }
                }
            },
            "snapshot": {
                "enabled": snapshot_enabled,
                "directory": snapshot_path
            }
        }

        self.completed = True
        if self.on_complete:
            self.on_complete(self.config_data)
        self.root.destroy()

    def run(self) -> bool:
        """运行向导，返回是否完成配置"""
        self.root.mainloop()
        return self.completed

    def get_config(self) -> Dict[str, Any]:
        """获取配置数据"""
        return self.config_data


def save_user_config(config: Dict[str, Any], path: str) -> bool:
    """保存用户配置到 YAML 文件"""
    if yaml is None:
        print("警告：未安装 PyYAML，无法保存配置")
        return False

    try:
        # 添加注释头
        content = "# 魔芋 用户配置文件\n# 此文件由配置向导自动生成，可手动编辑\n\n"
        content += yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False


def load_user_config(path: str) -> Optional[Dict[str, Any]]:
    """加载用户配置"""
    if yaml is None or not os.path.exists(path):
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None


if __name__ == "__main__":
    # 测试向导
    def on_complete(cfg):
        print("配置完成：", cfg)
        save_user_config(cfg, "user_config.yml")

    wizard = SetupWizard(on_complete=on_complete)
    if wizard.run():
        print("向导完成")
    else:
        print("向导跳过")
