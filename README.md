# lip-voice

口パク（声を出さない口の動き）をカメラで読み取り、登録した定型フレーズを判定して音声で再生するアプリ。
声を失ったが口は動かせる人（気管切開後の ALS 患者など）が、自分のフレーズを自分専用のモデルで認識させることを目指す。

## 特徴
- **利用者の PC の中だけで動く。ネットがなくても動く**（初回に顔検出のモデルを取得するときだけネットが必要）
- 顔全体の映像は PC の外に出さない。保存するのは口元の切り出しと特徴点だけ
- 利用者のデータで学習し、口の動きの変化に合わせて再学習できる
- データはプロフィールごとのフォルダに保存。バックアップは Google ドライブの同期フォルダへ（予定）

## 状態
ステップ2a（収集基盤）まで実装済み。学習・評価・認識画面（2b）、バックアップ（2c）、常時監視と夜間アラート（ステップ3）はこれから。
詳細は [docs/spec.md](docs/spec.md)。以前の Google ログイン + Cloud Run 版は、コミット `e83e7e7` までの履歴に残っている。

## セットアップ（開発: Mac / Linux）
Python 3.10 以上、Node 22 以上が必要。
```
scripts/setup-dev.sh          # Python の環境、画面のビルド、顔検出モデルの取得
app/.venv/bin/lipvoice run --open
```
- カメラの番号を調べる: `lipvoice cameras`。指定して起動: `lipvoice run --source 1`
- 動画ファイルをカメラの代わりに使う（試験用）: `lipvoice run --source 動画.mp4`
- 1 フレームあたりの処理時間を測る（実機の負荷の確認）: `lipvoice bench --seconds 20`
- データの整合性を検査する: `lipvoice check`（`--repair` で孤児ファイルを退避）
- Mac では初回に、ターミナル（または使っているアプリ）にカメラの許可を出す

## 収集の手順（フェーズ1: 開発者の顔で Mac から）
```
app/.venv/bin/lipvoice --profile developer run --open
```
- スペースキーを押して離すと録画が始まり、口が止まって 1 秒（または 10 秒）で自動で終わる。Enter＝保存、Backspace＝撮り直し
- 収集の計画は `docs/spec.md` の 9章（3 日分）。負例（あくび、咳など）は画面の「フレーズではない動き」で録る
- 患者さん本人のデータは、本人の PC（プロフィールを分ける）で、特徴点だけを保存する。動画をそのまま PC の外に出さない

## データの置き場所
`~/LipVoice/<プロフィール>/`（`LIPVOICE_HOME` と `--profile` で変更）。中身は `config.json`、`lipvoice.db`、`clips/`、`models/`。
1 クリップは約 200KB（250 本で約 50MB）。開発者のテストデータと本人のデータは、別のプロフィールにする。

## 開発
```
cd app && .venv/bin/python -m pytest        # テスト
cd web && npm run dev                       # 画面の開発（別端末で LIPVOICE_TOKEN=dev lipvoice run --dev、VITE_LIPVOICE_TOKEN=dev）
```

## 安全上の前提
- 緊急の呼び出しはこの仕組みに頼らない。既存の手段を併用する
- 自動発話は、取り違えが少ないと確認できるまで OFF
- 顔由来のデータは、OS のディスク暗号化で守る（Mac は FileVault、Windows はデバイスの暗号化）

## ライセンス
MIT
