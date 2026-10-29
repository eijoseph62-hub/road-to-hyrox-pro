# SAYAKA: 継続開発と実行手順

## 現在の状態

- 第1段階: AGENTS.mdは導入済み。
- 第2段階: 単一FITのCRC検証、日付・単位確認、重複排除した非公開履歴、比較、レビュー用JSON、V5.1動画・ZIP、形式・音声一致の検証まで実装。
- 第3段階: テキストチャット画面と認証・利用制限付きローカルバックエンドを実装。外部ホスティング、API接続、本番公開は未実施。
- 音声: 決定済みV5.1の共通メッセージを無変更で利用。毎回の分析文の読み上げとリアルタイム音声会話は未実装。新しい声を勝手に選ばない。

## FITからレビュー用成果物まで

Python 3.10以降、FFmpeg/ffprobeを使用。

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
python -m sayaka prepare /path/to/activity.fit --out outputs/run --assets /path/to/private-assets
```

素材フォルダには承認済みの `approved-v51.mp4` と `NotoSansCJKjp-Regular.otf` を置く。
`config/assets-manifest.json` で今回確認した素材のハッシュと照合する。素材は公開GitHubに追加しない。
素材を取得できない場合は動画を捏造せず、`--assets` を省略してFIT解析まで進める。
素材は既存の保存済みV5.1 ZIPにも含まれる。ファイルの存在を必ず確認する。

会話をまたぐ履歴と素材は、次の非公開チェックポイントに保存する:

```sh
python -m sayaka checkpoint --assets /path/to/private-assets --out outputs/SAYAKA-private-state.zip
```

CodexはこのZIPを非公開の保存先に保存し、ファイルリンクを渡す。コードはGitHub、履歴と素材はこのZIPで引き継ぐ。
新しい会話では、利用可能な添付・選択済みファイルを使う。過去の会話のファイルが自動で見えるとは仮定しない。

`private/history.json` に実測集計のみを保存。GPS、氏名、原本FITは公開しない。
同じ開始日時・距離・タイマー時間の記録は1件にまとめる。並列prepareは実行しない。
実測履歴が不足する場合、距離や速さが改善したとは断定しない。
新規の分析は保守的な初期案。コーチは練習目的・CrossFit負荷・疲労を確認して必要に応じ修正する。
すでに公開した分析と全計測値が一致する場合は、その承認済み文言を維持する。
任意の文言は `--analysis analysis.json`、短い動画文言は `--video-copy copy.json` で渡す。
動画用初期文言は固定の保守的な案であり、任意の長文分析を自動要約する機能ではない。
カスタム分析時は動画文言も整合させてレビューする。

成果物:

出力先は毎回新しいフォルダを指定する。既存の成果物があるフォルダへのprepareは失敗させ、古い動画と新しい分析が混在するのを防ぐ。

- `training-data.json`: 既存サイトと同じスキーマの公開候補。
- `report.json`: 実測値・比較根拠・未公開状態。
- `video-copy.json`: 短い動画文言。
- MP4、MP4を含むZIP、`quality.json`、3時点のコンタクトシート。

自動検査の合格と人による音声付き目視レビューは区別する。
文字の重なり、古い文字、誤読、カード内の収まりを最後に確認する。
長い文言はエラーにし、フォントを縮小したりデザインを変えたりしない。

## 公開の境界

公開前に変更内容をユーザーへ示す。承認後のみ:

```sh
python -m sayaka apply outputs/run --approved
```

このコマンドはローカルの `training-data.json` のみを置き換える。GitHubに自動送信しない。
Codexが承認済みの同ファイルだけをGitHubへ反映し、配信されたJSONも取得して一致確認する。
ダウンロードは成功が確認された保存経路でMP4を保存し、返されたファイルリンクを渡す。
ローカルのffprobe成功だけをダウンロード成功とは呼ばない。

## テキストチャット

```sh
export OPENAI_API_KEY='secure-server-secret'
export OPENAI_MODEL='your-enabled-model'
export SAYAKA_ACCESS_TOKEN='random-owner-access-token-at-least-24-characters'
python -m sayaka serve
```

環境変数の例はダミー。キーをこのリポジトリやブラウザへ保存しない。
`http://127.0.0.1:8787/` で確認。環境変数が足りなければ送信は無効のままにする。
初期上限は1分4回・日本時間の日次20回、入力1メッセージ1500文字、返答最大800トークン。
回数制限はSQLiteに保存し、再起動・並列リクエストでも維持する。失敗したAPI呼び出しも回数に含める。
会話内容やアクセスコードはサーバーのログに保存しない。ブラウザの会話・コードもメモリのみ。
現在の公開分析と直近10件の検証済み履歴だけをコンテキストにする。APIは `store:false`。
回数・トークン上限は金額によるハード上限ではない。提供元の予算制限も別途設定する。

本番化にはHTTPSホスト、永続ストレージ、本人認証、APIキーの安全な接続、利用予算、実APIとの疎通確認が必要。
このサーバーはループバック限定の実装で、外部公開用の完成ホスティングではない。
GitHub Pagesに `coach.html` を置くだけでは会話は動作しない。そのため既存トップの導線はまだ変更しない。
公開構成を確定してから、同一オリジンのHTTPS経路・Origin検査・認証を適切に移行する。

Realtime音声は次の段階。現在の承認済み声を利用できることは未確認であり、別の標準音声に置き換えない。

## 検証

```sh
python -m unittest discover -s tests -v
node --check coach.js
```

API呼び出しはテストではモックを使用。課金APIの実接続試験とは区別する。
本番のHTML、`training-data.json`、`sayaka.mp4` はこの開発で変更しない。
