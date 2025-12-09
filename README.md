# Focus Guard 🛡️👀

轻量级跨平台（Windows / macOS）“防偷窥”小工具：用摄像头检测画面里是否出现多张人脸，触发后会切换到你的工作软件，并可抓拍留证。

## ✨ 功能亮点
- 📸 MediaPipe 高精度人脸检测，支持多帧稳定判断，默认“多人同屏”才触发。
- 🪟 顶层小预览窗：可移动/缩放，检测到人脸时显示提示文字。
- 💾 抓拍留存：触发时保存当前画面到自定义目录。
- 🔀 自动切 App：按配置激活 VSCode / IDEA 等常用软件。
- ⚙️ 配置覆盖：打包内置默认配置，exe 同目录放精简 `config.json` 即可覆盖想改的字段，其他参数沿用默认值。

## 🛠️ 环境准备
1) 安装 Python 3.9+  
   - Windows：推荐官方安装包或 Microsoft Store。  
   - macOS：`brew install python`

2) 克隆并安装依赖
```bash
git clone <your-repo-url> moyu
cd moyu
python -m pip install -r requirements.txt
```
（mac 用 `python3` 命令即可）

## 🚀 源码运行（开发调试）
```bash
python main.py
```
首运行需允许摄像头权限。关闭小窗口即可退出。

## 🧩 配置说明（内置 + 覆盖）
- 程序启动时先加载打包内置的 `config.json`，再尝试读取 exe 同目录的外部 `config.json`，用其中字段递归覆盖内置值。**外部文件可以只写你想改的项**。
- Windows 路径可用正斜杠或单反斜杠：`C:/Users/you/Pictures/people` 或 `C:\Users\you\Pictures\people`（无需双反斜杠）。

### 常用字段
- `min_faces_for_alert`：触发所需最少人脸数。默认 2，如需单人触发改成 1。
- `alert_cooldown_seconds`：两次触发间的冷却秒数。
- `snapshot.enabled`：是否抓拍；`snapshot.directory`：保存目录（不存在会自动创建）。
- `work_app.active`：当前生效的目标；`work_app.targets.*.windows_command / macos_command`：对应系统的启动/激活命令。
- 摄像头高级参数（亮度、对比度、面积过滤等）如不写，使用内置默认。

### 覆盖示例（最小化配置）
放在 exe 同目录的 `config.json`：
```json
{
  "min_faces_for_alert": 1,
  "work_app": {
    "active": "idea",
    "targets": {
      "idea": {
        "windows_command": "C:/Program Files/JetBrains/IntelliJ IDEA/bin/idea64.exe"
      }
    }
  },
  "snapshot": {
    "enabled": true,
    "directory": "snapshots"
  }
}
```
其余未写字段自动沿用内置配置。

## 📦 打包（Windows）
> 需在 Windows 环境执行，mac 版必须在 mac 上打包。

1) 安装 PyInstaller（在虚拟环境内）：
```bash
python -m pip install pyinstaller
```
2) 生成无控制台、单文件 exe（含内置配置与 mediapipe 数据）：
```bash
python -m PyInstaller --onefile --noconsole --add-data "config.json;." --collect-data mediapipe main.py
```
3) 产物位于 `dist/main.exe`。把需要覆盖的 `config.json` 放在与 `main.exe` 同目录即可。

## 🍎 打包（macOS）
在 mac 上执行（Win 无法跨编译 mac）：
```bash
python3 -m pip install pyinstaller
python3 -m PyInstaller --onefile --noconsole --add-data "config.json:." --collect-data mediapipe main.py
```
产物为 `dist/main`。首次运行如被 Gatekeeper 拦截，可右键打开或自行签名/公证。

## ❓ 常见问题
- 看不到日志：`--noconsole` 版本不会在终端输出，如需调试可去掉 `--noconsole` 重新打包，或在终端运行 exe 观察输出。
- 触发却无抓拍：确认 `snapshot.enabled=true`、保存目录可写；`min_faces_for_alert` 是否符合场景（默认 2，单人需改 1）。
- 摄像头打不开（MSMF 报错等）：关闭占用摄像头的软件，检查系统摄像头权限；必要时在代码中改用 `cv2.CAP_DSHOW` 再打包。

尽情使用，欢迎反馈体验！ 🎉
