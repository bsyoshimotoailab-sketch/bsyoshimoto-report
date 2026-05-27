# BSよしもと 視聴率レポートシステム — デプロイ手順書

## 概要

ブラウザでURLを開くだけで使えるWebアプリです。
@yoshimoto.co.jp のGoogleアカウントでログインした人のみ使えます。

---

## 初回セットアップ（1回だけ）

### STEP 1: Google Cloudでサービスアカウントを作成

1. https://console.cloud.google.com を開く
2. プロジェクト「ratings-auto」を選択
3. 左メニュー「IAMと管理」→「サービスアカウント」
4. 「サービスアカウントを作成」をクリック
5. 名前：`ratings-app`、説明：`Streamlitアプリ用` → 「作成して続行」
6. ロール：「編集者」を選択 → 「完了」
7. 作成されたサービスアカウントをクリック
8. 「キー」タブ → 「キーを追加」→「新しいキーを作成」→「JSON」
9. ダウンロードされた JSONファイルを保存（後で使います）

### STEP 2: DriveフォルダをサービスアカウントとShareする

1. https://drive.google.com/drive/folders/1JIKlOBc42pUTHhHaShInWo_YT_9-GmrJ を開く
2. フォルダを右クリック→「共有」
3. STEP1でダウンロードしたJSONの `client_email` の値を入力
   （例：ratings-app@ratings-auto-492703.iam.gserviceaccount.com）
4. 権限：「編集者」→「送信」

### STEP 3: GitHubにコードをアップロード

1. https://github.com を開いてログイン
2. 「New repository」→名前：`bsyoshimoto-report`→「Create repository」
3. このフォルダの全ファイルをドラッグ＆ドロップしてアップロード
   ※ `service_account.json` は絶対にアップロードしない！

### STEP 4: Streamlit Cloudにデプロイ

1. https://share.streamlit.io を開く
2. GitHubアカウントでログイン
3. 「New app」→リポジトリ：`bsyoshimoto-report`→ブランチ：`main`→ファイル：`app.py`
4. 「Advanced settings」→「Secrets」に以下を貼り付け：

```toml
[google_service_account]
type = "service_account"
project_id = "ratings-auto-492703"
private_key_id = "（JSONファイルのprivate_key_id）"
private_key = "（JSONファイルのprivate_key）"
client_email = "（JSONファイルのclient_email）"
client_id = "（JSONファイルのclient_id）"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "（JSONファイルのclient_x509_cert_url）"

summaries_folder_id = "1JIKlOBc42pUTHhHaShInWo_YT_9-GmrJ"
```

5. 「Deploy!」をクリック → 5〜10分でデプロイ完了

### STEP 5: アクセス制限設定（@yoshimoto.co.jpのみ）

1. Streamlit Cloudの管理画面でアプリを選択
2. 「Settings」→「Sharing」
3. 「Restricted」を選択
4. 許可するメールアドレスまたはドメイン：`@yoshimoto.co.jp` を追加
5. 「Save」

---

## 毎週の使い方

1. ブラウザで https://（あなたのアプリURL）.streamlit.app を開く
2. `@yoshimoto.co.jp` のGoogleアカウントでログイン
3. レポートタイプを選択：
   - **① 週次レポート**：「Google Driveから自動取得」✅のまま → 「レポートを生成する」
   - **② 番宣効果検証**：CSVと番宣Excelをアップロード → 「生成」
   - **③ クール総括マクロ**：対象年・クールを選択 → 「生成」
4. PDFダウンロードボタンをクリック

---

## トラブルシューティング

**「DriveにCSVが見つかりません」と表示される**
→ スタッフにratingsフォルダへのCSVアップロードを依頼してください

**「サービスアカウントが見つかりません」エラー**
→ Streamlit CloudのSecretsが正しく設定されているか確認してください

**PDF生成に時間がかかる**
→ 2〜3分かかります。そのまま待ってください。

**アプリが「Zzz... sleeping」と表示される**
→ 数日アクセスがないとスリープします。クリックすれば1分で復帰します。
