; ============================================================
; setup.iss   Inno Setup スクリプト（Inno Setup 6 用）
;
; PyInstaller の出力（..\dist\GifVideoConverter）を、
; 単一の .exe インストーラーにまとめる。
;
; 特徴:
;   - インストール先は %appdata%\GifVideoConverter（管理者権限不要）
;   - デスクトップショートカットはチェックボックスで任意選択（既定OFF）
;   - スタートメニューのショートカットは常に作成
;   - 全ファイルは LZMA 圧縮で Setup.exe 内に格納され、
;     インストール確定時にのみ展開される（軽量な単一インストーラー）
;
; ビルド方法:
;   A) GUI: Inno Setup Compiler でこのファイルを開き [Build]→[Compile]
;   B) コマンド: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss
;
; ※ このファイルは日本語を含むため UTF-8 (BOM 付き) で保存すること。
; ============================================================

; ---- 定数定義（配布前にここを自分の値へ変更）----
#define MyAppName "GIF Video Converter"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Your Company"
#define MyAppExeName "GifVideoConverter.exe"

[Setup]
; AppId はアプリを一意に識別する GUID。バージョンを跨いで固定にすること。
AppId={{A7B3C9D1-2E4F-4A6B-8C0D-1E2F3A4B5C6D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

; インストール先を %appdata%\GifVideoConverter に固定
DefaultDirName={userappdata}\GifVideoConverter
DefaultGroupName={#MyAppName}

; 管理者権限を要求しない（ユーザー領域へのインストールのため）
PrivilegesRequired=lowest

; 出力される単一インストーラー
OutputDir=Output
OutputBaseFilename=GifVideoConverter_Setup

; 圧縮設定：確定まで圧縮状態で内包し、インストーラーを軽量化
Compression=lzma2/max
SolidCompression=yes

; 見た目・ウィザード設定
WizardStyle=modern
DisableProgramGroupPage=yes
; インストール先選択画面は表示する（変更したいユーザー向け）
DisableDirPage=no

[Languages]
; インストーラー UI を日本語にする
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
; デスクトップショートカットのチェックボックス（既定OFF = unchecked）
Name: "desktopicon"; Description: "デスクトップにショートカットを作成する"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; dist\GifVideoConverter\ 配下を構造ごと丸ごと同梱
; （EXE 本体・_internal・bin の ffmpeg・templates・static などすべて）
Source: "..\dist\GifVideoConverter\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; スタートメニューのショートカット（常に作成）
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; スタートメニューにアンインストールのショートカット
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; デスクトップのショートカット（チェックボックスが ON のときのみ）
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; インストール完了直後に起動するかを選べるチェックボックス
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
