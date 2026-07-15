// ============================================================================
// app.js
// フロントエンドの操作ロジック。
// ファイル選択 -> 設定 -> 変換 -> 進捗ポーリング -> 結果 の一連の流れを制御する。
// ============================================================================

(function () {
    "use strict";

    // ---- 定数 ----
    var ALLOWED_EXTENSIONS = ["mp4", "gif"];
    var MAX_FILE_SIZE = 500 * 1024 * 1024; // 500MB
    var POLL_INTERVAL_MS = 700;            // 進捗ポーリング間隔

    // ---- 状態 ----
    var selectedFile = null;   // 選択中のファイル
    var currentTaskId = null;  // 実行中タスクの ID
    var pollTimer = null;      // ポーリング用タイマー

    // ---- 要素参照 ----
    var el = {
        notice:        document.getElementById("notice"),
        stepSelect:    document.getElementById("step-select"),
        stepSettings:  document.getElementById("step-settings"),
        stepProgress:  document.getElementById("step-progress"),
        stepResult:    document.getElementById("step-result"),

        dropzone:      document.getElementById("dropzone"),
        fileInput:     document.getElementById("file-input"),
        browseBtn:     document.getElementById("browse-btn"),

        selectedName:  document.getElementById("selected-name"),
        selectedSize:  document.getElementById("selected-size"),
        clearFileBtn:  document.getElementById("clear-file-btn"),

        srcFormat:     document.getElementById("src-format"),
        dstFormat:     document.getElementById("dst-format"),

        fpsControl:    document.getElementById("fps-control"),
        fpsSlider:     document.getElementById("fps-slider"),
        fpsValue:      document.getElementById("fps-value"),

        qualitySlider: document.getElementById("quality-slider"),
        qualityValue:  document.getElementById("quality-value"),

        convertBtn:    document.getElementById("convert-btn"),

        progressMessage: document.getElementById("progress-message"),
        progressFill:    document.getElementById("progress-fill"),
        progressPercent: document.getElementById("progress-percent"),
        cancelBtn:       document.getElementById("cancel-btn"),

        downloadLink:      document.getElementById("download-link"),
        newConversionBtn:  document.getElementById("new-conversion-btn")
    };

    // ---- ユーティリティ ----

    // 拡張子を小文字で取得
    function getExtension(name) {
        var idx = name.lastIndexOf(".");
        if (idx === -1) { return ""; }
        return name.slice(idx + 1).toLowerCase();
    }

    // バイト数を読みやすい単位に変換
    function formatSize(bytes) {
        if (bytes < 1024) { return bytes + " B"; }
        if (bytes < 1024 * 1024) { return (bytes / 1024).toFixed(1) + " KB"; }
        return (bytes / (1024 * 1024)).toFixed(1) + " MB";
    }

    // 通知メッセージを表示（type: "error" | "success"）
    function showNotice(message, type) {
        el.notice.textContent = message;
        el.notice.className = "notice notice-" + type;
        el.notice.hidden = false;
    }

    // 通知メッセージを隠す
    function hideNotice() {
        el.notice.hidden = true;
    }

    // 表示ステップを切り替える
    function showStep(step) {
        el.stepSelect.hidden   = (step !== "select");
        el.stepSettings.hidden = (step !== "settings");
        el.stepProgress.hidden = (step !== "progress");
        el.stepResult.hidden   = (step !== "result");
    }

    // ---- ファイル選択処理 ----

    // ファイルを検証して受け入れる
    function acceptFile(file) {
        hideNotice();

        var ext = getExtension(file.name);
        // 形式チェック
        if (ALLOWED_EXTENSIONS.indexOf(ext) === -1) {
            showNotice("対応していない形式です（.mp4 または .gif を選択してください）", "error");
            return;
        }
        // サイズチェック
        if (file.size > MAX_FILE_SIZE) {
            showNotice("ファイルサイズが上限（500MB）を超えています", "error");
            return;
        }
        if (file.size === 0) {
            showNotice("空のファイルは変換できません", "error");
            return;
        }

        selectedFile = file;
        renderSettings(ext);
        showStep("settings");
    }

    // 設定画面を描画する
    function renderSettings(ext) {
        el.selectedName.textContent = selectedFile.name;
        el.selectedSize.textContent = formatSize(selectedFile.size);

        // 変換方向を自動判定して表示
        var target = (ext === "mp4") ? "GIF" : "MP4";
        el.srcFormat.textContent = ext.toUpperCase();
        el.dstFormat.textContent = target;

        // フレームレート設定は GIF 生成時（MP4 -> GIF）のみ表示
        el.fpsControl.hidden = (ext !== "mp4");
    }

    // ファイル選択をリセットする
    function clearFile() {
        selectedFile = null;
        el.fileInput.value = "";
        hideNotice();
        showStep("select");
    }

    // ---- 変換開始 ----

    function startConversion() {
        if (!selectedFile) { return; }

        hideNotice();
        el.convertBtn.disabled = true;

        var formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("fps", el.fpsSlider.value);
        formData.append("quality", el.qualitySlider.value);

        fetch("/api/convert", { method: "POST", body: formData })
            .then(function (res) { return res.json().then(function (data) { return { ok: res.ok, data: data }; }); })
            .then(function (result) {
                el.convertBtn.disabled = false;
                if (!result.ok || !result.data.success) {
                    showNotice(result.data.error || "変換の開始に失敗しました", "error");
                    return;
                }
                // 変換開始成功 -> 進捗画面へ
                currentTaskId = result.data.task_id;
                showStep("progress");
                resetProgressView();
                startPolling();
            })
            .catch(function () {
                el.convertBtn.disabled = false;
                showNotice("サーバーに接続できませんでした", "error");
            });
    }

    // 進捗表示を初期化
    function resetProgressView() {
        el.progressFill.style.width = "0%";
        el.progressPercent.textContent = "0%";
        el.progressMessage.textContent = "変換を準備しています";
        el.cancelBtn.disabled = false;
    }

    // ---- 進捗ポーリング ----

    function startPolling() {
        stopPolling();
        pollTimer = setInterval(pollStatus, POLL_INTERVAL_MS);
        pollStatus(); // すぐ1回実行
    }

    function stopPolling() {
        if (pollTimer) {
            clearInterval(pollTimer);
            pollTimer = null;
        }
    }

    function pollStatus() {
        if (!currentTaskId) { return; }

        fetch("/api/status/" + currentTaskId)
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (!data.success) {
                    stopPolling();
                    showNotice(data.error || "進捗の取得に失敗しました", "error");
                    showStep("settings");
                    return;
                }
                updateProgressView(data);
            })
            .catch(function () {
                // 一時的な通信エラーはポーリング継続（致命ではない）
            });
    }

    // 進捗データを画面に反映
    function updateProgressView(data) {
        el.progressMessage.textContent = data.message || "変換中です";
        var pct = Math.max(0, Math.min(100, data.progress || 0));
        el.progressFill.style.width = pct + "%";
        el.progressPercent.textContent = pct + "%";

        if (data.status === "done") {
            stopPolling();
            showResult(data.result_filename);
        } else if (data.status === "error") {
            stopPolling();
            showNotice(data.message || "変換中にエラーが発生しました", "error");
            showStep("settings");
        } else if (data.status === "canceled") {
            stopPolling();
            showNotice("変換をキャンセルしました", "success");
            showStep("settings");
        }
    }

    // ---- キャンセル ----

    function cancelConversion() {
        if (!currentTaskId) { return; }
        el.cancelBtn.disabled = true;

        fetch("/api/cancel/" + currentTaskId, { method: "POST" })
            .then(function (res) { return res.json(); })
            .then(function () {
                // 実際の状態遷移はポーリングで受け取る
            })
            .catch(function () {
                el.cancelBtn.disabled = false;
                showNotice("キャンセルに失敗しました", "error");
            });
    }

    // ---- 結果表示 ----

    function showResult(filename) {
        el.downloadLink.href = "/downloads/" + encodeURIComponent(filename);
        el.downloadLink.setAttribute("download", filename);
        showStep("result");
    }

    // 最初からやり直す
    function resetAll() {
        stopPolling();
        currentTaskId = null;
        clearFile();
    }

    // ---- スライダーの値表示更新 ----

    el.fpsSlider.addEventListener("input", function () {
        el.fpsValue.textContent = el.fpsSlider.value + " fps";
    });
    el.qualitySlider.addEventListener("input", function () {
        el.qualityValue.textContent = el.qualitySlider.value + "%";
    });

    // ---- ドラッグ＆ドロップ ----

    el.dropzone.addEventListener("dragover", function (e) {
        e.preventDefault();
        el.dropzone.classList.add("dragover");
    });
    el.dropzone.addEventListener("dragleave", function () {
        el.dropzone.classList.remove("dragover");
    });
    el.dropzone.addEventListener("drop", function (e) {
        e.preventDefault();
        el.dropzone.classList.remove("dragover");
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            acceptFile(e.dataTransfer.files[0]);
        }
    });

    // クリックでファイル選択
    el.dropzone.addEventListener("click", function () { el.fileInput.click(); });
    el.browseBtn.addEventListener("click", function (e) {
        e.stopPropagation();
        el.fileInput.click();
    });
    // キーボード操作（Enter / Space）でも開けるようにする
    el.dropzone.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            el.fileInput.click();
        }
    });
    el.fileInput.addEventListener("change", function () {
        if (el.fileInput.files && el.fileInput.files.length > 0) {
            acceptFile(el.fileInput.files[0]);
        }
    });

    // ---- ボタンイベント ----
    el.clearFileBtn.addEventListener("click", clearFile);
    el.convertBtn.addEventListener("click", startConversion);
    el.cancelBtn.addEventListener("click", cancelConversion);
    el.newConversionBtn.addEventListener("click", resetAll);

    // 初期表示
    showStep("select");
})();
