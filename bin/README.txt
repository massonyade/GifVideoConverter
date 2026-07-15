このフォルダに ffmpeg 実行ファイルを配置してください。

必要なファイル:
  - ffmpeg.exe
  - ffprobe.exe

入手方法:
  1. https://www.gyan.dev/ffmpeg/builds/ または https://ffmpeg.org/download.html
     から Windows 向けビルド（例: ffmpeg-release-essentials.zip）をダウンロード
  2. 展開して bin\ffmpeg.exe と bin\ffprobe.exe を、このフォルダにコピー

配置後の構成イメージ:
  gif-video-converter/
    └── bin/
        ├── ffmpeg.exe
        └── ffprobe.exe

補足:
  - このフォルダに実行ファイルが無い場合、アプリは環境変数 PATH 上の
    ffmpeg / ffprobe を探して使用します（開発環境向けのフォールバック）。
  - 配布（EXE / MSI）する場合は、必ずこのフォルダに同梱してください。
    build.spec がこの bin フォルダを EXE に含めます。
