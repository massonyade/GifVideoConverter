# -*- mode: python ; coding: utf-8 -*-
"""
build.spec
PyInstaller によるビルド設定ファイル。

このファイルは Windows 上で以下のコマンドを実行してビルドする:
    pyinstaller build.spec

生成物:
    dist/GifVideoConverter/GifVideoConverter.exe  （onedir 形式）

ポイント:
  - templates / static / bin をデータとして同梱する
  - bin/ に ffmpeg.exe と ffprobe.exe を事前に配置しておくこと
  - MSI 化（WiX）では onedir 形式のフォルダをそのままパッケージ化するのが容易
"""

import os

block_cipher = None

# プロジェクトのルートディレクトリ
project_root = os.path.abspath(".")

# 同梱するデータファイル（(元パス, 展開先フォルダ名) のタプル）
added_datas = [
    (os.path.join(project_root, "templates"), "templates"),
    (os.path.join(project_root, "static"), "static"),
    (os.path.join(project_root, "bin"), "bin"),
]


a = Analysis(
    ["app.py"],                 # エントリポイント
    pathex=[project_root],
    binaries=[],
    datas=added_datas,
    hiddenimports=[
        "flask",
        "jinja2",
        "werkzeug",
        "click",
        "itsdangerous",
        "markupsafe",
    ],
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
    [],
    exclude_binaries=True,
    name="GifVideoConverter",   # 実行ファイル名
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,              # コンソール（黒窓）を表示しない GUI アプリ扱い
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="installer/app.ico",  # アイコンを付ける場合はコメントを外す
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="GifVideoConverter",   # dist/GifVideoConverter/ フォルダに出力される
)
