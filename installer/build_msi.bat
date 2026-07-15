@echo off
rem ============================================================
rem build_msi.bat  （WiX Toolset v4/v5/v6/v7 用）
rem
rem PyInstaller の出力（..\dist\GifVideoConverter）を MSI にまとめる。
rem 前提:
rem   - .NET SDK インストール済み
rem   - wix ツール導入済み        : dotnet tool install --global wix
rem   - UI 拡張 導入済み          : wix extension add -g WixToolset.UI.wixext
rem installer フォルダ内でこのバッチを実行すること。
rem ============================================================

setlocal

set SOURCE_DIR=..\dist\GifVideoConverter

rem 出力フォルダの存在チェック
if not exist "%SOURCE_DIR%" (
    echo [エラー] %SOURCE_DIR% が見つかりません。
    echo 先に  python -m PyInstaller build.spec  を実行してください。
    exit /b 1
)

echo MSI をビルドしています...
wix build product.wxs -ext WixToolset.UI.wixext -d SourceDir="%SOURCE_DIR%" -o GifVideoConverter.msi
if errorlevel 1 goto error

echo.
echo 完了しました： installer\GifVideoConverter.msi
goto end

:error
echo.
echo [エラー] MSI の生成に失敗しました。
echo   - wix --version が動くか
echo   - wix extension list に WixToolset.UI.wixext があるか
echo を確認してください。
exit /b 1

:end
endlocal
