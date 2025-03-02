#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
XUnity大模型翻译v3打包脚本
此脚本用于将模块化的程序打包为可执行文件(.exe)

使用方法:
1. 安装必要的打包工具：pip install -r requirements.txt
2. 运行此脚本：python build_exe.py
3. 打包完成后，可在dist文件夹中找到可执行文件
"""

import os
import sys
import shutil
import subprocess
import time
import platform

# 配置项
APP_NAME = "XUnity大模型翻译ver3.1"
MAIN_SCRIPT = "main.py"
VERSION = "1.0.0"

# 打印欢迎信息
print("="*60)
print(f"欢迎使用 {APP_NAME} 打包工具")
print("="*60)
print(f"操作系统: {platform.system()} {platform.release()} ({platform.architecture()[0]})")
print(f"Python版本: {platform.python_version()}")
print("="*60)
print()

# 检查主脚本是否存在
if not os.path.exists(MAIN_SCRIPT):
    print(f"错误: 找不到主脚本文件 {MAIN_SCRIPT}")
    print("请确保在正确的目录中运行此脚本")
    sys.exit(1)

# 检查模块化目录是否存在
required_dirs = ["core", "ui"]
for directory in required_dirs:
    if not os.path.isdir(directory):
        print(f"错误: 找不到必要的目录 {directory}")
        print("请确保在正确的目录中运行此脚本")
        sys.exit(1)

# 确保PyInstaller已安装
try:
    import PyInstaller
    print(f"PyInstaller版本: {PyInstaller.__version__}")
except ImportError:
    print("PyInstaller未安装，正在尝试安装...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print("PyInstaller安装完成")
    except subprocess.CalledProcessError:
        print("错误: PyInstaller安装失败")
        print("请尝试手动安装: pip install pyinstaller")
        sys.exit(1)

# 检查其他依赖
print("正在检查依赖项...")
required_packages = ["requests", "ttkbootstrap"]
for package in required_packages:
    try:
        __import__(package)
        print(f"√ {package} 已安装")
    except ImportError:
        print(f"× {package} 未安装，正在尝试安装...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"  {package} 安装完成")
        except subprocess.CalledProcessError:
            print(f"错误: {package} 安装失败")
            print(f"请尝试手动安装: pip install {package}")
            sys.exit(1)

# 直接开始打包，无需用户确认
print("\n所有依赖检查完毕，开始打包...")

# 清理旧的构建文件
print("\n正在清理旧的构建文件...")
try:
    if os.path.exists("build"):
        shutil.rmtree("build")
        print("- 已删除build目录")
    if os.path.exists("dist"):
        shutil.rmtree("dist")
        print("- 已删除dist目录")
    spec_file = f"{APP_NAME}.spec"
    if os.path.exists(spec_file):
        os.remove(spec_file)
        print(f"- 已删除{spec_file}文件")
except Exception as e:
    print(f"警告: 清理文件时出错: {str(e)}")
    print("继续打包流程...")

# 构建命令
print("\n正在准备打包命令...")
cmd = [
    "pyinstaller",
    "--name", APP_NAME,
    "--onefile",  # 打包成单个可执行文件
    "--windowed",  # 不显示控制台窗口
    "--noconfirm",  # 不进行确认
    "--clean",  # 清理临时文件
]

# 添加必要的数据文件
if os.path.exists("config.ini"):
    cmd.extend(["--add-data", "config.ini;."])
    print("包含配置文件: config.ini")

# 添加模块目录
cmd.extend(["--add-data", "core;core"])
cmd.extend(["--add-data", "ui;ui"])
print("包含核心模块目录: core, ui")

# 添加隐式导入的模块，确保它们被包含在打包中
hidden_imports = ["queue", "concurrent.futures", "tkinter", "ttkbootstrap", 
                  "configparser", "json", "urllib.parse", "re", "socket", 
                  "http.server", "socketserver", "threading", "winreg"]
for module in hidden_imports:
    cmd.extend(["--hidden-import", module])

# 添加主脚本
cmd.append(MAIN_SCRIPT)

# 显示完整命令
print("\n将执行以下命令:")
print(" ".join(cmd))
print()

# 执行打包命令
print("="*60)
print("开始打包程序...")
print("="*60)
start_time = time.time()

try:
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # 检查是否成功
    if result.returncode != 0:
        print("打包过程中出现错误:")
        print(result.stderr)
        sys.exit(1)
    else:
        # 打印输出，但过滤一些不必要的信息
        for line in result.stdout.split('\n'):
            if "INFO: " not in line and line.strip():
                print(line)
except Exception as e:
    print(f"执行打包命令时出错: {str(e)}")
    sys.exit(1)

# 计算耗时
elapsed_time = time.time() - start_time
minutes = int(elapsed_time // 60)
seconds = int(elapsed_time % 60)

# 在dist目录中复制额外文件
print("\n正在复制附加文件...")
try:
    # 创建dist目录（如果不存在）
    if not os.path.exists("dist"):
        os.makedirs("dist")
        
    # 复制README
    if os.path.exists("README.md"):
        shutil.copy("README.md", os.path.join("dist", "README.md"))
        print("- 已复制README.md")
    
    # 复制配置文件（如果不是通过--add-data添加）
    if os.path.exists("config.ini") and "--add-data" not in " ".join(cmd):
        shutil.copy("config.ini", os.path.join("dist", "config.ini"))
        print("- 已复制config.ini")
except Exception as e:
    print(f"警告: 复制附加文件时出错: {str(e)}")

# 检查打包结果
exe_path = os.path.join("dist", f"{APP_NAME}.exe")
if os.path.exists(exe_path):
    exe_size = os.path.getsize(exe_path) / (1024 * 1024)  # 转换为MB
    print(f"\n可执行文件大小: {exe_size:.2f} MB")
else:
    print("\n警告: 找不到生成的可执行文件，打包可能失败")

print("\n" + "="*60)
print(f"打包完成! 耗时: {minutes}分{seconds}秒")
print(f"可执行文件位置: {os.path.abspath(exe_path)}")
print("="*60)
print("\n使用说明:")
print("1. 直接双击exe文件即可运行程序")
print("2. 首次在新环境运行时，如果提示缺少DLL，可能需要安装Visual C++ Redistributable")
print("3. 程序会在同一目录下自动创建并使用config.ini存储配置")

print("\n如果启动时出现闪退，请尝试在命令行中运行以查看错误信息:")
print(f"cd {os.path.abspath('dist')} && {APP_NAME}.exe")
print("\n祝您使用愉快!")

# 在Windows上，保持窗口打开
if platform.system() == "Windows":
    input("\n按Enter键退出...") 