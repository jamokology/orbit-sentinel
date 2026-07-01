# GeoVigil Analytics — Handoff Note

> 次スレッド（コンテキスト引き継ぎ用）の作業開始ガイド。
> 背景・理由は [CONCEPT_NOTE.md](CONCEPT_NOTE.md)、仕様は [ARCHITECTURE.md](ARCHITECTURE.md) を参照。
> この3点セットを「コアドキュメント」と呼ぶ。

最終更新: 2026-07-01

---

## 直近の決定事項

1. 前任者モデル（Faster R-CNN、ブラジル178枚）は出発点として使うが、そのままでは実運用不可と評価済み
2. データセット拡充は **Active Learning方式**：既存モデル検出500枚＋NDVI変化検出500枚をスタッフ確認 → 元178枚と合わせて再学習
3. **Sentinel-2の独立YOLOモデルは作らない**。Sentinel-2は変化検出による早期警戒のみ、NICFIが本検出（YOLO、形状判定）を担う
4. ステータス遷移ロジック確定（`active`/`unconfirmed`/`inactive`、優先順位つき）— 詳細は ARCHITECTURE.md の Detection Record Lifecycle
5. **WBF（Weighted Boxes Fusion）はほぼ不要の方向。** Sentinel-2変化検出の出力形式が座標点＋スコアに確定したため、近接マッチングのみで足りる見込み（最終確定は未）
6. Sentinel-2変化検出の候補フィルタ・パラメータ調整方式が確定。詳細はCONCEPT_NOTE.md「Sentinel-2変化検出の出力形式と候補フィルタ」参照
7. Sentinel単独検出の信頼度は固定値ではなく**検出ごとの可変信頼度**（較正曲線）に変更
8. **ARCHITECTURE.mdの反映待ち：** Pipeline Execution節・Overview図・Output Format（`source`フィールド）がまだWBF前提の記述のまま。上記5,6,7の確定を受けて更新が必要（次スレッドのタスク1）
9. **候補レビュー用のスワイプ判定サイトを構築・デプロイ済み。** `review/`配下、Cloudflare Pages + Functions + D1（判定結果）+ R2（画像）。本番URL: https://geovigil-review.pages.dev 。名前入力＋合言葉認証、True/False/Hold判定、同時アクセス時の排他制御（claim）、結果集計ページ（`/results.html`）あり。詳細は`review/README.md`参照
10. **Global Forest Watch（GFW）をSentinel-2と並行する早期警戒ソースとして追加することを決定。** GFWは`active`格上げ不可（Sentinel-2と同じ役割）。信頼度較正曲線はSentinel-2とは別に作る。Sentinel-2×GFW同時検出時の信頼度ブーストは、恣意的な固定値ではなく統計的モデル（ロジスティック回帰等でP(TP\|Sentinel-2マージン, GFW特徴量)を推定）が正当化できる場合のみ採用。詳細はCONCEPT_NOTE.md「Global Forest Watch（GFW）連携と付加特徴量」参照
11. **Slope・河川/村からの距離データをCandidateメタデータとして保持することを決定。** 事前の除外フィルタとしては使わず、正誤ラベル蓄積後に統計的相関が確認できた場合のみ信頼度算出に組み込む
12. **レビュー対象総数を1700枚に再整理。** 目的別にステップ2（早期警戒ロジック較正、NICFI不使用、計700枚＝Sentinel-2候補500＋GFW差分100＋Sentinel-2単独100）とステップ3（YOLO学習データ収集、NICFI使用、計1000枚＝既存モデル検出500＋Sentinelトリガー確認500）に再編。詳細はCONCEPT_NOTE.md「構築フロー（改訂）」参照
13. **GFWの内実を確認：** GLAD-L（Landsat 30m）/GLAD-S2（Sentinel-2 10m）/RADD（Sentinel-1 SAR 10m、雲の影響なし）の統合であり、解像度・更新頻度は統一されていない。RADDはCC BY 4.0で無料公開されているが、SAR処理の専門性・実装コストの観点から、今回は自前実装せずGFW/RADDの既成アラートを使う方針を確認。自前Sentinel-1レイヤーは将来検討事項としてCONCEPT_NOTE.md「未決事項」に記録
14. **クラウド実行への移行は見送り。** ワークステーション（共有PC + Task Scheduler）は単一障害点だが、無料・週次運用という前提の下ではクラウド実行（GPU推論の実行時間コスト）が無料枠に収まらないため、現行構成を維持する
15. **`detections.json`直書き＋git pushから、DBへの切り替えに合意。** 検出件数増加後のdiffレビュー困難・スキーマ拡張性の問題を見越した判断。移行先（Cloudflare D1等）・移行タイミング（パイプライン実装前 vs 後）は未確定 — 次スレッドで検討
16. **マルチテンポラル拡張を採用（確定・2026-07-01、2026-07-01訂正）。** 元178枚＋ステップ2aでTRUE確認された地点について、3ヶ月前・6ヶ月前・9ヶ月前のNICFIモザイク（地点あたり3枚追加＝計4倍）を追加取得する。**自動Positiveラベル付けはせず、通常のステップ2/3と同じスタッフT/Fレビューに回す**（元は真陽性地点でも過去時点ではFalseになりうるため）。地点単位train/val分割が条件。詳細はCONCEPT_NOTE.md「ステップ3c」参照
17. **Sentinel-1（SAR）は独立モデルではなく、Sentinel-2変化検出への追加特徴量として統合を検討する方向に確定。** 滑走路の平滑面による後方散乱の弱さを特徴量化し、ステップ2データでNDVIマージンとの予測力向上を統計検証。相関確認できればGFWと同じロジスティック回帰の枠組みで統合、できなければメタデータ保持のみ。詳細はCONCEPT_NOTE.md参照
18. **Coca crop/field検出（道路をキーとするアプローチ）を将来構想として記録（今回は着手しない）。** 道路検出自体の難易度が高いため。詳細はCONCEPT_NOTE.md「未決事項」参照

---

## 次スレッドでやること（優先順）

### 1. ARCHITECTURE.mdをこのスレッドの決定に合わせて更新
- Overview図の「Ensemble via WBF」、Pipeline Executionのディレクトリ構成（`ensemble.py`）と実行ステップ（「Merge results with WBF」）を、WBFほぼ不要の方針に合わせて修正
- Output Formatの`source`フィールド値（`"Ensemble (Sentinel-2 + Planet)"`）の要否を再検討
- `confidence`フィールドの意味（NICFI検出のモデル信頼度 と Sentinel単独検出の可変信頼度で性質が異なる点）を明記するか検討
- **GFWを第3の検出ソースとして追加**（Satellite Imagery Sources節、Models節、Output Formatの`source`フィールド値に`"GFW"`を追加）

### 2. NDVI変化検出ロジックの実装
- 出力形式・候補フィルタ条件・構築フロー（日付例つき）は確定済み（CONCEPT_NOTE.md「Sentinel-2変化検出の出力形式と候補フィルタ」参照）
- 残タスク：対象範囲（ペルー全土 or 試験的に一部地域）、各フィルタの初期パラメータ（NDVI閾値、アスペクト比閾値、直線性の許容残差、最小長さ）
- 直線性・最小長さ・アスペクト比の実装（`skimage.measure.regionprops`, `skimage.morphology.skeletonize`等を想定）

### 3. 既存Faster-RCNNモデルでの推論バッチ実行（構築フロー ステップ3a）
- `data/original_files/illegal_runway_detection_training.py` のモデル構造を参照
- 信頼度閾値なしで全検出を出力 → NICFI画像（構築フロー例：2025-06-15）に対して候補500件を抽出
- 学習済み重みファイル（.pth）の所在を確認（前任者から未受領の可能性、ARCHITECTURE.md Pending Items参照）

### 4. GFW API連携の実装
- GFW APIの認証方式・提供される特徴量（confidenceレベル等）を確認
- 汎用GFWクライアントモジュールとして実装（将来のCoca Crop予測等でも再利用する想定）
- ステップ2b（GFW検出・Sentinel-2未検出の差分100枚）・2c（Sentinel-2検出・GFW未検出100枚）の候補抽出ロジックを実装

### 5. スタッフ確認フローの準備（レビューサイトは構築済み、`review/README.md`参照）
- レビューサイト（`review/`）は稼働中。現状はダミー画像のみ投入済みなので、実データのバッチを`py/pipeline/upload_candidates.py`で投入する
- ステップ2（計700枚：Sentinel-2候補500＋GFW差分100＋Sentinel-2単独100）とステップ3（計1000枚：既存モデル検出500＋NICFI確認500）、合計1700枚を順次投入
- 各バッチのsource値を`sentinel_candidate`/`existing_model`/`sentinel_triggered_nicfi`に加え、GFW関連の値（例：`gfw_diff`/`sentinel_only`）を追加する必要あり（`review/schema.sql`のCHECK制約はないため追加は容易だが、集計ページ・アップロードスクリプトのsource一覧を更新すること）
- ステップ2aの正誤結果は、TP変化量分布から99.9%信頼度で閾値を外挿決定するために使う
- ステップ3bの正誤結果は、2aの500枚とプール（計1000枚）して99.9%信頼度を再計算し、かつ可変信頼度の較正曲線を作るために使う（CONCEPT_NOTE.md「構築フロー」参照）。パラメータ再調整は1回で打ち切り、反復しない
- ステップ2bの正誤結果はGFW較正曲線の構築に、2c（Sentinel-2単独）との比較はSentinel-2×GFW信頼度ブーストの統計的検証に使う

### 6. Slope・河川/村距離データの入手
- データ提供元・形式をスタッフに確認（CONCEPT_NOTE.md「Slope・河川/村からの距離データ」参照）
- Candidateデータ（レビューサイトの`candidates`テーブル含む）への紐付け方法を設計

### 7. YOLO再学習
- 178枚＋確認済み陽性・陰性（既存モデル500＋NICFIトリガー確認500）を合わせてYOLOデータセットを構築（計1178枚）
- 3b由来サンプルには「Sentinelトリガー由来」タグを付与（信頼度算出用ではなく将来のトレーサビリティ目的）
- COCO→YOLO形式変換が必要（`labelme2coco_ada.py` がCOCO変換部分の参考になる）
- NIRバンド込みで学習するかどうか要検討（CONCEPT_NOTE.md「データセット拡充の方針」参照、4バンド画像を活かす案）

---

## 読むべきファイル（前任者データ）

`data/original_files/` 配下：

| ファイル | 内容 | 読了状況 |
|---|---|---|
| `illegal_runway_detection_training.py` | Faster R-CNN訓練コード | 読了 |
| `Faster-RCNN illegal runway detection_model_training_report.pdf` | 訓練レポート（epoch/lr等、コードと一部不一致あり） | 読了 |
| `ReadMe_Illegal_Runway_Dataset.pdf` | データソース・COCOフォーマット・信頼性評価の説明 | 読了 |
| `labelme2coco_ada.py` | Labelme→COCO変換スクリプト | 未読 |
| `shp to tif.pdf` | シェープファイル→TIFF変換手順 | 未読 |
| `dataset.json` | COCOアノテーション本体 | 未読（重いため） |

---

## 確認が必要な未解決事項

- 前任者の学習済みモデル重みファイル（`FRN_30epochs_CompleteDataset_2ndround.pth` 等）を受領しているか
- コード（30 epoch, lr=0.001）とレポート（100 epoch, lr=0.005）のどちらが最終モデルの実際の設定か、前任者に確認できるか
- Planet NICFI GEE APIアクセス、Copernicus Data Space APIの取得状況
