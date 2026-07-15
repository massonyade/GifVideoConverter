# -*- coding: utf-8 -*-
"""
converter.py
ffmpeg を用いた MP4 <-> GIF 変換処理と、変換タスクの状態管理を行うモジュール。

- タスクは一意な task_id で管理し、進捗（0-100%）・状態・結果を保持する
- 変換は別スレッドで実行し、ffmpeg の -progress 出力を解析して進捗を更新する
- キャンセル要求があれば ffmpeg プロセスを停止する
"""

import os
import re
import shutil
import subprocess
import threading
import uuid

import config


# ---- ffmpeg / ffprobe の実行パス解決 ------------------------------------

def _find_binary(name):
    """
    ffmpeg / ffprobe の実行ファイルを探索する。

    優先順位:
      1. 実行ファイルと同じ場所の bin/ フォルダ（配布時に同梱する想定）
      2. 環境変数 PATH 上のコマンド

    見つからなければ最終的にコマンド名だけを返し、
    実行時に PATH から解決させる（開発環境向けフォールバック）。
    """
    exe_name = name + (".exe" if os.name == "nt" else "")
    # 1. 同梱 bin/ を優先
    bundled = os.path.join(config.base_dir(), "bin", exe_name)
    if os.path.isfile(bundled):
        return bundled
    # 2. PATH 上を探索
    found = shutil.which(name)
    if found:
        return found
    # フォールバック（PATH に任せる）
    return name


FFMPEG = _find_binary("ffmpeg")
FFPROBE = _find_binary("ffprobe")

# Windows でコンソールウィンドウを表示しないためのフラグ
# （PyInstaller の --noconsole ビルドで子プロセスの黒窓が出るのを防ぐ）
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _subprocess_kwargs():
    """subprocess 実行時の共通オプションを返す。"""
    kwargs = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.STDOUT,
        "universal_newlines": True,
        "encoding": "utf-8",
        "errors": "replace",
    }
    if os.name == "nt":
        kwargs["creationflags"] = _CREATE_NO_WINDOW
    return kwargs


# ---- タスク管理 ----------------------------------------------------------

# task_id -> タスク情報 の辞書。複数スレッドから触るのでロックで保護する。
_tasks = {}
_tasks_lock = threading.Lock()


def create_task():
    """新しいタスクを登録し、task_id を返す。"""
    task_id = uuid.uuid4().hex
    with _tasks_lock:
        _tasks[task_id] = {
            "status": "pending",   # pending / processing / done / error / canceled
            "progress": 0,          # 0-100
            "message": "待機中です",
            "result_filename": None,
            "process": None,        # 実行中の ffmpeg プロセス（キャンセル用）
            "canceled": False,
        }
    return task_id


def get_task(task_id):
    """task_id からタスク情報のコピーを返す。存在しなければ None。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is None:
            return None
        # 外部に process オブジェクトは渡さない（内部管理用のため除外）
        return {
            "status": task["status"],
            "progress": task["progress"],
            "message": task["message"],
            "result_filename": task["result_filename"],
        }


def _update_task(task_id, **kwargs):
    """タスク情報を安全に更新する内部ヘルパー。"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is not None:
            task.update(kwargs)


def cancel_task(task_id):
    """
    タスクをキャンセルする。
    実行中の ffmpeg プロセスがあれば強制終了する。
    戻り値: キャンセルを受け付けたら True、対象が無ければ False。
    """
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is None:
            return False
        task["canceled"] = True
        process = task["process"]
    # ロックの外でプロセス停止（terminate がブロックする可能性に配慮）
    if process is not None and process.poll() is None:
        try:
            process.terminate()
        except Exception:
            pass
    return True


# ---- ffprobe による総再生時間の取得 -------------------------------------

def _get_duration_seconds(input_path):
    """
    入力ファイルの総再生時間（秒）を ffprobe で取得する。
    取得できない場合は 0.0 を返す（その場合は進捗を推定できない）。
    """
    cmd = [
        FFPROBE,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        input_path,
    ]
    try:
        kwargs = _subprocess_kwargs()
        # ffprobe は短時間で終わるので check_output 相当で取得
        result = subprocess.run(cmd, **kwargs)
        text = (result.stdout or "").strip()
        return float(text)
    except Exception:
        return 0.0


# ---- ffmpeg コマンドの組み立て -------------------------------------------

def _build_mp4_to_gif_palette_cmds(input_path, output_path, palette_path, fps, quality):
    """
    MP4 -> GIF 変換用の 2 パス（パレット生成 + パレット適用）コマンドを組み立てる。

    パレット方式を用いることで、単純変換より大幅に画質を向上できる。
    品質（quality）は出力解像度の倍率にマッピングし、
    100% で元解像度、低いほど縮小して軽量化する。
    """
    # 品質を 0.5～1.0 の解像度スケールに変換
    scale_ratio = 0.5 + (quality - config.MIN_QUALITY) / (config.MAX_QUALITY - config.MIN_QUALITY) * 0.5
    scale_ratio = max(0.5, min(1.0, scale_ratio))
    # 幅を偶数に丸める（-1 で高さは自動計算）
    scale_expr = "scale=trunc(iw*{r}/2)*2:-1:flags=lanczos".format(r=round(scale_ratio, 3))

    # パス1: パレット生成
    palette_cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-vf", "fps={fps},{scale},palettegen=stats_mode=diff".format(fps=fps, scale=scale_expr),
        palette_path,
    ]

    # パス2: パレット適用（進捗はこちらで取得する）
    convert_cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-i", palette_path,
        "-lavfi",
        "fps={fps},{scale}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle".format(
            fps=fps, scale=scale_expr
        ),
        "-progress", "pipe:1", "-nostats",
        output_path,
    ]
    return palette_cmd, convert_cmd


def _build_gif_to_mp4_cmd(input_path, output_path, quality):
    """
    GIF -> MP4 変換用コマンドを組み立てる。

    - yuv420p / faststart で幅広いプレイヤーとの互換性を確保
    - 幅・高さを偶数に丸める（H.264 の制約対応）
    - 品質は CRF（数値が小さいほど高画質）にマッピングする
    """
    # 品質(30-100%) を CRF(28-18) に反比例で対応させる
    crf = int(round(28 - (quality - config.MIN_QUALITY) / (config.MAX_QUALITY - config.MIN_QUALITY) * 10))
    crf = max(18, min(28, crf))

    cmd = [
        FFMPEG, "-y",
        "-i", input_path,
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        "-crf", str(crf),
        "-progress", "pipe:1", "-nostats",
        output_path,
    ]
    return cmd


# ---- 進捗付きで ffmpeg を実行 -------------------------------------------

# ffmpeg -progress の out_time_us / out_time_ms 行を検出する正規表現
_OUT_TIME_RE = re.compile(r"out_time_(?:ms|us)=(\d+)")
_PROGRESS_END_RE = re.compile(r"progress=end")


def _run_with_progress(task_id, cmd, total_seconds, base_progress, span_progress):
    """
    ffmpeg を実行し、-progress 出力を解析してタスク進捗を更新する。

    base_progress : このパス開始時点の進捗基準（%）
    span_progress : このパスが占める進捗の幅（%）

    戻り値: 正常終了なら True、失敗またはキャンセルなら False。
    """
    kwargs = _subprocess_kwargs()
    process = subprocess.Popen(cmd, **kwargs)

    # キャンセル用にプロセスを登録
    _update_task(task_id, process=process)

    # 出力を1行ずつ読み進捗を更新
    for line in process.stdout:
        # キャンセル要求のチェック
        with _tasks_lock:
            canceled = _tasks.get(task_id, {}).get("canceled", False)
        if canceled:
            try:
                process.terminate()
            except Exception:
                pass
            break

        if total_seconds > 0:
            m = _OUT_TIME_RE.search(line)
            if m:
                # out_time_us はマイクロ秒、out_time_ms もキー名に反して
                # 実体はマイクロ秒を返す ffmpeg のバージョンがあるため
                # いずれも 1_000_000 で割って秒に換算する
                current_us = int(m.group(1))
                current_sec = current_us / 1_000_000.0
                ratio = min(1.0, current_sec / total_seconds)
                progress = int(base_progress + ratio * span_progress)
                _update_task(task_id, progress=min(99, progress))

    process.wait()

    # 登録解除
    _update_task(task_id, process=None)

    # キャンセルされていれば False
    with _tasks_lock:
        if _tasks.get(task_id, {}).get("canceled", False):
            return False

    return process.returncode == 0


# ---- 変換のメイン処理（別スレッドで実行される） -------------------------

def run_conversion(task_id, input_path, output_path, src_ext, dst_ext, fps, quality):
    """
    実際の変換処理を行う。app.py からスレッドで呼び出される想定。

    処理の流れ:
      1. 総再生時間を取得
      2. 変換方向に応じて ffmpeg を実行（GIF 生成時はパレット2パス）
      3. 進捗・状態を更新し、完了時に結果ファイル名を記録
      4. 成否に関わらず入力の一時ファイルを削除
    """
    palette_path = None
    try:
        _update_task(task_id, status="processing", progress=0, message="変換を準備しています")

        total_seconds = _get_duration_seconds(input_path)

        if src_ext == "mp4" and dst_ext == "gif":
            # --- MP4 -> GIF（2パス）---
            palette_path = output_path + ".palette.png"
            palette_cmd, convert_cmd = _build_mp4_to_gif_palette_cmds(
                input_path, output_path, palette_path, fps, quality
            )

            # パス1: パレット生成（全体の 0-15% を割り当て、進捗は簡易表示）
            _update_task(task_id, message="パレットを生成しています", progress=2)
            ok = _run_with_progress(task_id, palette_cmd, total_seconds, base_progress=0, span_progress=15)
            if not ok:
                _finish_as_canceled_or_error(task_id, "パレット生成に失敗しました")
                return

            # パス2: パレット適用（15-100%）
            _update_task(task_id, message="GIF に変換しています", progress=15)
            ok = _run_with_progress(task_id, convert_cmd, total_seconds, base_progress=15, span_progress=84)
            if not ok:
                _finish_as_canceled_or_error(task_id, "GIF への変換に失敗しました")
                return

        elif src_ext == "gif" and dst_ext == "mp4":
            # --- GIF -> MP4 ---
            _update_task(task_id, message="MP4 に変換しています", progress=2)
            cmd = _build_gif_to_mp4_cmd(input_path, output_path, quality)
            ok = _run_with_progress(task_id, cmd, total_seconds, base_progress=0, span_progress=99)
            if not ok:
                _finish_as_canceled_or_error(task_id, "MP4 への変換に失敗しました")
                return
        else:
            # 想定外の組み合わせ
            _update_task(task_id, status="error", message="対応していない変換形式です")
            return

        # 出力ファイルが実際に生成されたか確認
        if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
            _update_task(task_id, status="error", message="変換結果ファイルが生成されませんでした")
            return

        _update_task(
            task_id,
            status="done",
            progress=100,
            message="変換が完了しました",
            result_filename=os.path.basename(output_path),
        )

    except FileNotFoundError:
        # ffmpeg / ffprobe が見つからない場合
        _update_task(
            task_id,
            status="error",
            message="ffmpeg が見つかりません。bin フォルダに ffmpeg を配置してください",
        )
    except Exception as exc:  # noqa: BLE001  想定外エラーもユーザーに通知する
        _update_task(task_id, status="error", message="変換中にエラーが発生しました: {}".format(exc))
    finally:
        # 一時ファイル（入力・パレット）を削除する
        _safe_remove(input_path)
        if palette_path:
            _safe_remove(palette_path)


def _finish_as_canceled_or_error(task_id, error_message):
    """
    パス失敗時に、キャンセル由来か通常エラーかを判定して状態を確定する。
    """
    with _tasks_lock:
        canceled = _tasks.get(task_id, {}).get("canceled", False)
    if canceled:
        _update_task(task_id, status="canceled", message="変換をキャンセルしました")
    else:
        _update_task(task_id, status="error", message=error_message)


def _safe_remove(path):
    """例外を無視してファイルを削除する。"""
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass
