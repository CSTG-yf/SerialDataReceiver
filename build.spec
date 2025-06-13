# build.spec
block_cipher = None
project_path = r'D:\SerialDataReceiver'

a = Analysis(
    ['main.py'],
    pathex=['D:\SerialReceiver'],  # 修改为你的项目路径
    binaries=[],
    datas=[
        (r'D:\SerialDataReceiver\icon\myapp.ico', 'icon'),  # 添加ico图标
        (r'D:\SerialDataReceiver\icon\\app_window.svg', 'icon')  # 添加svg图标
    ],
    hiddenimports=['PyQt5.QtCore', 'PyQt5.QtGui', 'PyQt5.QtWidgets', 'serial'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SerialMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 设置为 False 不显示控制台窗口
    icon=os.path.join(project_path, 'icon', 'myapp.ico'),  # 指定图标文件路径
distpath=project_path,
    workpath=os.path.join(project_path, 'build')
)