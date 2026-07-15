# -*- coding: utf-8 -*-
"""
config.py
アプリケーション全体の設定値を一元管理するモジュール。

PyInstaller で EXE 化した場合と、通常の Python 実行の両方で
正しくパスを解決できるように resource_path() / base_dir() を用意している。
"""

import os
import sys


def base_dir():
    """
    実行ファイル（またはスクリプト）が置かれているディレクトリを返す。

    - PyInstaller で凍結（frozen）されている場合は EXE のあるフォルダ
    - 通常実行の場合はこのファイルのあるフォルダ

    アップロード用・ダウンロード用など「書き込みが必要」なフォルダは
    このディレクトリを基準にする。
    """
    if getattr(sys, "frozen", False):
        # PyInstaller で生成された EXE として実行されている場合
        return os.path.dirname(sys.executable)
    # 通常の Python スクリプトとして実行されている場合
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(relative_path):
    """
    テンプレートや静的ファイルなど「読み取り専用でバンドルされる」
    リソースの絶対パスを返す。

    PyInstaller の onefile モードでは、リソースは一時展開フォルダ
    （sys._MEIPASS）に置かれるため、そちらを優先して参照する。
    """
    if hasattr(sys, "_MEIPASS"):
        # PyInstaller が展開した一時フォルダ
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)


# ---- ディレクトリ設定 ----------------------------------------------------

# 一時アップロードファイルの保存先
UPLOAD_DIR = os.path.join(base_dir(), "uploads")

# 変換済みファイルの保存先
DOWNLOAD_DIR = os.path.join(base_dir(), "downloads")

# 起動時にディレクトリが無ければ作成する
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)


# ---- ファイル制約 --------------------------------------------------------

# 許可する拡張子（この2種類のみ処理する）
ALLOWED_EXTENSIONS = {"mp4", "gif"}

# アップロードファイルサイズの上限（500MB）
MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 * 1024 * 1024 バイト

# 変換方向の対応表（入力拡張子 -> 出力拡張子）
CONVERSION_MAP = {
    "mp4": "gif",
    "gif": "mp4",
}


# ---- 変換パラメータの既定値・範囲 ---------------------------------------

# フレームレート（GIF 生成時）の許容範囲
MIN_FPS = 5
MAX_FPS = 30
DEFAULT_FPS = 15

# 品質（%）の許容範囲
MIN_QUALITY = 30
MAX_QUALITY = 100
DEFAULT_QUALITY = 80


# ---- 一時ファイルの自動削除設定 -----------------------------------------

# この秒数を過ぎた一時ファイルは自動削除の対象になる（既定：1時間）
FILE_TTL_SECONDS = 60 * 60

# 自動削除チェックを行う間隔（秒）
CLEANUP_INTERVAL_SECONDS = 10 * 60


# ---- サーバー設定 --------------------------------------------------------

HOST = "127.0.0.1"   # ローカル専用（外部公開しない）
PORT = 5000
