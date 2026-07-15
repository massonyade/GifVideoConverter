# GIF ↔ 動画 変換ツール

MP4 と GIF を相互に変換する、Flask 製のローカルデスクトップツールです。
ブラウザ UI で操作し、変換処理は端末内の ffmpeg で完結します。最終的に
Windows の `.msi` インストーラーとして配布することを想定しています。

## 主な機能

- MP4 → GIF（パレット2パスによる高画質変換）
- GIF → MP4（yuv420p / faststart で高い互換性）
- ドラッグ＆ドロップ / クリックでのファイル選択
- フレームレート（5–30fps）・品質（30–100%）のスライダー調整
- リアルタイム進捗表示（0–100%）とキャンセル
- 500MB のサイズ上限、拡張子ホワイトリスト、ファイル名サニタイズ
- 一時ファイルの自動削除

## フォルダ構成

```
gif-video-converter/
├── app.py              … Flask 本体（REST API・ルーティング）
├── converter.py        … ffmpeg 変換ロジック・タスク管理
├── config.py           … 設定値・パス解決
├── requirements.txt    … 依存パッケージ
├── build.spec          … PyInstaller ビルド設定
├── templates/
│   └── index.html      … UI 画面
├── static/
│   ├── css/style.css   … スタイル
│   └── js/app.js       … フロント操作ロジック
├── bin/                … ffmpeg.exe / ffprobe.exe を配置（要ダウンロード）
├── uploads/            … 一時アップロード（自動生成・自動削除）
├── downloads/          … 変換結果（自動生成・自動削除）
└── installer/
    ├── product.wxs     … WiX による MSI 定義
    └── build_msi.bat   … MSI ビルド用バッチ
```

## API 仕様

| メソッド | パス | 説明 |
| --- | --- | --- |
| POST | `/api/convert` | ファイル・形式・パラメータを受け取り変換タスクを開始。`task_id` を返す |
| GET | `/api/status/<task_id>` | 進捗（0–100%）・状態・結果ファイル名を返す |
| POST | `/api/cancel/<task_id>` | 変換をキャンセル |
| GET | `/downloads/<filename>` | 変換済みファイルをダウンロード |

---

## 1. 開発環境での実行

### 前提

- Python 3.9 以上
- ffmpeg / ffprobe（`bin/` に配置、または PATH 上に用意）

### 手順

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# ffmpeg の準備（bin/README.txt 参照）
#   bin/ffmpeg.exe と bin/ffprobe.exe を配置
#   ※ 開発中は PATH 上の ffmpeg があれば bin/ は省略可

# 起動
python app.py
```

起動すると自動で既定ブラウザが開き、`http://127.0.0.1:5000/` で UI が表示されます。

---

## 2. EXE 化（PyInstaller）

Windows 上で以下を実行します。

```bash
# 1. bin/ に ffmpeg.exe と ffprobe.exe を必ず配置しておく
# 2. ビルド
pyinstaller build.spec
```

`dist/GifVideoConverter/GifVideoConverter.exe` が生成されます。
このフォルダごと配布すれば、Python 未インストールの環境でも動作します。

> `console=False` でビルドしているため、実行時にコンソールの黒い窓は表示されません。

---

## 3. MSI インストーラー化（WiX Toolset v3）

PyInstaller の出力（`dist/GifVideoConverter/`）を MSI にまとめます。

### 前提

- [WiX Toolset v3](https://wixtoolset.org/) をインストール
- `heat.exe` / `candle.exe` / `light.exe` に PATH が通っていること

### 手順

```bat
cd installer
build_msi.bat
```

`installer/GifVideoConverter.msi` が生成されます。
このバッチは内部で次を行います。

1. `heat.exe` … `dist` 配下の全ファイルを WiX コンポーネント化（`AppFiles.wxs`）
2. `candle.exe` … `product.wxs` と `AppFiles.wxs` をコンパイル
3. `light.exe` … MSI へリンク（スタートメニュー／デスクトップのショートカット付き）

### 配布前に見直す項目（`installer/product.wxs`）

- `Manufacturer` … 発行者名
- `UpgradeCode` … 製品を一意に識別する GUID（バージョン間で固定にする）
- `Version` … 製品バージョン

---

## セキュリティについて

- サーバーは `127.0.0.1`（ローカルのみ）で待ち受け、外部公開しません
- アップロードは `.mp4` / `.gif` のみ許可、サイズ上限 500MB
- ファイル名は `secure_filename` + UUID でサニタイズ
- ダウンロードは `downloads/` 直下に限定し、パストラバーサルを防止
- `task_id` は UUID 形式のみ受理

## ライセンス上の注意

ffmpeg を同梱・再配布する場合は、ffmpeg 自体のライセンス（LGPL/GPL）に従って
ください。ビルド構成によって条件が異なります。
