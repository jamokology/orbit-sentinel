# GeoVigil Analytics — 違法滑走路検出システム

衛星画像AIによるペルー国内の違法滑走路候補地の検出・可視化Webアプリ

## 概要

麻薬・鉱物密輸に使われる違法滑走路をペルー警察が効率的に発見できるよう、衛星画像をAIで解析してその結果を地図上に表示するシステムです。

設計の詳細（アーキテクチャ・検出ロジック・意思決定の背景）は [doc/ARCHITECTURE.md](doc/ARCHITECTURE.md)・[doc/CONCEPT_NOTE.md](doc/CONCEPT_NOTE.md)・[doc/HANDOFF.md](doc/HANDOFF.md) を参照してください。

## 機能

- ペルー全土の地図にAI検知マーカーを一覧表示
- 確率スライダーで信頼度によるフィルタリング
- マーカークリックで検知確率・日時・座標をポップアップ表示
- 検出ステータス（`active` / `unconfirmed` / `inactive`）に応じたインジケーター表示
- 日本語 / 英語切り替え

## セットアップ（Webダッシュボードのローカル確認）

`web/` はビルド不要の静的サイトです。任意のローカルサーバーで配信して確認できます。

```bash
cd web
python3 -m http.server 8000
```

ブラウザで `http://localhost:8000` を開いてください。

## 技術スタック

| レイヤー | 技術 |
|------|-----------|
| Webダッシュボード | Vanilla JS + Leaflet |
| ホスティング | Cloudflare Pages（`main` push で自動デプロイ） |
| 検出パイプライン | Python 3.12（`py/`） |
| 物体検出 | YOLO（Ultralytics） |
| パッケージ管理 | uv |

## ディレクトリ構成

```
web/
  index.html          # ダッシュボード本体
  data/
    detections.json   # 検出結果データ（パイプラインが出力）
py/
  pipeline/           # 衛星画像取得・推論・マージ・JSON更新・git push
  daily_run.py        # パイプライン実行エントリポイント
doc/
  ARCHITECTURE.md     # システム構成の詳細
  CONCEPT_NOTE.md      # 設計判断の背景
  HANDOFF.md           # 作業引き継ぎメモ
```
