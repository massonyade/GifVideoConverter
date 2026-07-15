# -*- coding: utf-8 -*-
"""
app.py
Flask による REST API のエントリポイント。

提供エンドポイント:
  GET  /                         : フロントエンド（index.html）を返す
  POST /api/convert              : ファイルを受け取り変換タスクを開始
  GET  /api/status/<task_id>     : 変換進捗（0-100%）を返す
  POST /api/cancel/<task_id>     : 変換をキャンセル
  GET  /downloads/<filename>     : 変換済みファイルをダウンロード

セキュリティ:
  - 拡張子ホワイトリスト（.mp4 / .gif のみ）
  - ファイルサイズ上限（500MB）
  - ファイル名サニタイズ（secure_filename + UUID）
  - ダウンロード時のパストラバーサル防止
"""

import os
import threading
import time
import uuid

from flask import (
    Flask,
    jsonify,
    request,
    send_from_directory,
    render_template,
    abort,
)
from werkzeug.utils import secure_filename

import config
import converter


# テンプレート・静的ファイルのパスを解決して Flask を初期化
app = Flask(
    __name__,
    template_folder=config.resource_path("templates"),
    static_folder=config.resource_path("static"),
)

# アップロードサイズの上限を Flask 側でも設定（超過時は 413 を返す）
app.config["MAX_CONTENT_LENGTH"] = config.MAX_FILE_SIZE


# ---- 共通ヘルパー --------------------------------------------------------

def _get_extension(filename):
    """ファイル名から小文字の拡張子（ドット無し）を取得する。"""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _is_allowed(filename):
    """許可された拡張子かどうかを判定する。"""
    return _get_extension(filename) in config.ALLOWED_EXTENSIONS


def _json_error(message, status_code):
    """統一フォーマットの JSON エラーレスポンスを返す。"""
    response = jsonify({"success": False, "error": message})
    response.status_code = status_code
    return response


# ---- ルーティング --------------------------------------------------------

@app.route("/")
def index():
    """トップページ（変換 UI）を返す。"""
    return render_template("index.html")


@app.route("/api/convert", methods=["POST"])
def api_convert():
    """
    ファイルを受け取り、変換タスクを開始する。

    リクエスト（multipart/form-data）:
      file    : 変換対象ファイル（必須）
      fps     : GIF 生成時のフレームレート（任意、5-30）
      quality : 品質（任意、30-100）

    レスポンス（JSON）:
      { "success": true, "task_id": "...", "target_format": "gif" }
    """
    # --- ファイルの存在チェック ---
    if "file" not in request.files:
        return _json_error("ファイルが選択されていません", 400)

    uploaded = request.files["file"]
    if uploaded.filename == "":
        return _json_error("ファイルが選択されていません", 400)

    # --- 拡張子（形式）チェック ---
    if not _is_allowed(uploaded.filename):
        return _json_error("対応していない形式です（.mp4 または .gif を選択してください）", 400)

    src_ext = _get_extension(uploaded.filename)
    dst_ext = config.CONVERSION_MAP.get(src_ext)
    if dst_ext is None:
        return _json_error("変換先の形式を判定できませんでした", 400)

    # --- パラメータの取得と範囲チェック ---
    fps = _parse_int_param(request.form.get("fps"), config.DEFAULT_FPS, config.MIN_FPS, config.MAX_FPS)
    quality = _parse_int_param(
        request.form.get("quality"), config.DEFAULT_QUALITY, config.MIN_QUALITY, config.MAX_QUALITY
    )

    # --- ファイル名のサニタイズ ---
    # secure_filename で危険な文字を除去し、さらに UUID を付与して衝突・推測を防ぐ
    safe_base = secure_filename(uploaded.filename) or "input"
    unique_id = uuid.uuid4().hex
    input_filename = "{}_{}".format(unique_id, safe_base)
    input_path = os.path.join(config.UPLOAD_DIR, input_filename)

    # --- 保存とサイズチェック ---
    uploaded.save(input_path)
    file_size = os.path.getsize(input_path)
    if file_size > config.MAX_FILE_SIZE:
        # 念のためサーバー側でも再チェック（保存後に削除）
        converter._safe_remove(input_path)
        return _json_error("ファイルサイズが上限（500MB）を超えています", 400)
    if file_size == 0:
        converter._safe_remove(input_path)
        return _json_error("空のファイルは変換できません", 400)

    # --- 出力ファイル名（入力と同じ UUID を用いて対応付け）---
    output_filename = "{}.{}".format(unique_id, dst_ext)
    output_path = os.path.join(config.DOWNLOAD_DIR, output_filename)

    # --- タスク登録と変換スレッド起動 ---
    task_id = converter.create_task()
    thread = threading.Thread(
        target=converter.run_conversion,
        args=(task_id, input_path, output_path, src_ext, dst_ext, fps, quality),
        daemon=True,
    )
    thread.start()

    return jsonify({"success": True, "task_id": task_id, "target_format": dst_ext})


@app.route("/api/status/<task_id>", methods=["GET"])
def api_status(task_id):
    """
    指定タスクの進捗を返す。

    レスポンス（JSON）:
      { "success": true, "status": "...", "progress": 0-100,
        "message": "...", "result_filename": "..." }
    """
    # task_id の形式チェック（16進32文字の UUID.hex のみ許可）
    if not _is_valid_task_id(task_id):
        return _json_error("不正なタスクIDです", 400)

    task = converter.get_task(task_id)
    if task is None:
        return _json_error("指定されたタスクが見つかりません", 404)

    return jsonify({
        "success": True,
        "status": task["status"],
        "progress": task["progress"],
        "message": task["message"],
        "result_filename": task["result_filename"],
    })


@app.route("/api/cancel/<task_id>", methods=["POST"])
def api_cancel(task_id):
    """指定タスクの変換をキャンセルする。"""
    if not _is_valid_task_id(task_id):
        return _json_error("不正なタスクIDです", 400)

    if converter.cancel_task(task_id):
        return jsonify({"success": True, "message": "キャンセルを受け付けました"})
    return _json_error("指定されたタスクが見つかりません", 404)


@app.route("/downloads/<filename>", methods=["GET"])
def download_file(filename):
    """
    変換済みファイルをダウンロードさせる。

    パストラバーサル（../ など）を防ぐため secure_filename で正規化し、
    DOWNLOAD_DIR 直下のファイルのみを対象にする。
    """
    safe_name = secure_filename(filename)
    if safe_name != filename:
        # サニタイズ前後で一致しない場合は不正とみなす
        abort(400)

    file_path = os.path.join(config.DOWNLOAD_DIR, safe_name)
    if not os.path.isfile(file_path):
        abort(404)

    return send_from_directory(config.DOWNLOAD_DIR, safe_name, as_attachment=True)


# ---- エラーハンドラ ------------------------------------------------------

@app.errorhandler(413)
def too_large(_error):
    """413（サイズ超過）を日本語 JSON で返す。"""
    return _json_error("ファイルサイズが上限（500MB）を超えています", 413)


@app.errorhandler(404)
def not_found(_error):
    """API パスの 404 を JSON で返す（HTML ページ以外）。"""
    if request.path.startswith("/api/") or request.path.startswith("/downloads/"):
        return _json_error("リソースが見つかりません", 404)
    return _error_html("ページが見つかりません", 404)


@app.errorhandler(400)
def bad_request(_error):
    """400（不正リクエスト）を JSON で返す。"""
    if request.path.startswith("/api/") or request.path.startswith("/downloads/"):
        return _json_error("不正なリクエストです", 400)
    return _error_html("不正なリクエストです", 400)


def _error_html(message, code):
    """簡易的な HTML エラーページを返す。"""
    return "<h1>{}</h1><p>{}</p>".format(code, message), code


# ---- パラメータ検証ヘルパー ---------------------------------------------

def _parse_int_param(value, default, min_value, max_value):
    """
    フォーム値を整数に変換し、範囲内に丸めて返す。
    変換できない場合は既定値を返す（不正値の拒否・防御）。
    """
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(min_value, min(max_value, parsed))


def _is_valid_task_id(task_id):
    """task_id が UUID.hex（16進32文字）かどうかを検証する。"""
    if not isinstance(task_id, str) or len(task_id) != 32:
        return False
    try:
        int(task_id, 16)
        return True
    except ValueError:
        return False


# ---- 一時ファイルの自動削除（バックグラウンド）--------------------------

def _cleanup_worker():
    """
    一定間隔で uploads / downloads を走査し、
    TTL を過ぎた古いファイルを削除するワーカースレッド。
    """
    while True:
        time.sleep(config.CLEANUP_INTERVAL_SECONDS)
        now = time.time()
        for directory in (config.UPLOAD_DIR, config.DOWNLOAD_DIR):
            try:
                for name in os.listdir(directory):
                    path = os.path.join(directory, name)
                    if not os.path.isfile(path):
                        continue
                    # 最終更新から TTL 秒以上経過していれば削除
                    if now - os.path.getmtime(path) > config.FILE_TTL_SECONDS:
                        converter._safe_remove(path)
            except Exception:
                # 走査失敗は無視して次回に回す
                pass


def start_background_tasks():
    """バックグラウンドの自動削除スレッドを開始する。"""
    cleanup_thread = threading.Thread(target=_cleanup_worker, daemon=True)
    cleanup_thread.start()


# ---- 起動 ----------------------------------------------------------------

def _open_browser():
    """少し待ってから既定ブラウザで UI を開く（デスクトップアプリ的な体験のため）。"""
    import webbrowser
    time.sleep(1.2)  # サーバー起動を待つ
    webbrowser.open("http://{}:{}/".format(config.HOST, config.PORT))


def main():
    """アプリを起動する。EXE 化した際もこの関数がエントリになる。"""
    start_background_tasks()

    # 開発用のリローダーが有効だと二重にブラウザが開くのを防ぐため、
    # debug=False（リローダー無効）の本構成でのみブラウザを開く
    threading.Thread(target=_open_browser, daemon=True).start()

    # ローカル専用サーバーとして起動（外部公開しない）
    # debug=False にして本番・配布時の情報漏えいを防ぐ
    app.run(host=config.HOST, port=config.PORT, debug=False, threaded=True)


if __name__ == "__main__":
    main()
