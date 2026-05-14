# Codex Desktop 自動同期（固定URL・OS別）

HTML抽出/API経由ではなく、**固定URLをそのまま固定**で使う前提です。  
OSごとにURLが異なるため、複数URLを `SOURCE_FILE_URLS` で列挙して監視・同期します。

## 変更ファイル

- `scripts/sync-codex-desktop.py`
  - `SOURCE_FILE_URLS`（または `--source-file-urls`）で複数エントリを処理
  - エントリキー（`key`）ごとに保存先を分離
  - `etag / Last-Modified / Content-Length` の組で差分判定（変更時のみ更新）
- `.github/workflows/sync-codex-desktop.yml`
  - `workflow_dispatch` + 定期実行（時間次）
  - 差分があれば自動コミット
- `.gitattributes`
  - `.dmg`, `.zip`, `.exe`, `.msi` を LFS 対象化

## ローカル実行

```bash
python3 scripts/sync-codex-desktop.py \
  --source-file-urls '{
    "macos-arm64": {
      "url": "https://persistent.oaistatic.com/codex-app-prod/Codex.dmg",
      "output_name": "Codex.dmg"
    },
    "macos-x64": {
      "url": "https://persistent.oaistatic.com/codex-app-prod/Codex-latest-x64.dmg",
      "output_name": "Codex-latest-x64.dmg"
    },
    "windows": {
      "url": "https://get.microsoft.com/installer/download/9PLM9XGG6VKS?cid=website_cta_psi",
      "output_name": "Codex Installer.exe"
    }
  }' \
  --download-root downloads \
  --state-path downloads/codex-desktop-sync-state.json
```

## GitHub Actions

- `.github/workflows/sync-codex-desktop.yml` の `SOURCE_FILE_URLS` を更新してください。  
- `workflow_dispatch` で手動実行、`schedule` で定期実行です。

## `SOURCE_FILE_URLS` 形式

- 推奨: JSON Object  

```json
{
  "macos-arm64": {
    "url": "https://persistent.oaistatic.com/codex-app-prod/Codex.dmg",
    "output_name": "Codex.dmg"
  },
  "macos-x64": {
    "url": "https://persistent.oaistatic.com/codex-app-prod/Codex-latest-x64.dmg",
    "output_name": "Codex-latest-x64.dmg"
  },
  "windows": {
    "url": "https://get.microsoft.com/installer/download/9PLM9XGG6VKS?cid=website_cta_psi",
    "output_name": "Codex Installer.exe"
  }
}
```

- 各エントリは `key` と `url` が必須。`output_name` は任意。
- `key` ごとに保存先は `downloads/<key>/` 以下になります。

## メタデータ / 出力

- 状態ファイル: `downloads/codex-desktop-sync-state.json`
- 出力内容: 
  - 更新時: `status: synced`
  - 変化なし: `status: no_change`

## 補足

- このURLは、**現時点で固定直リンクとして確認済み**です。
  - `https://persistent.oaistatic.com/codex-app-prod/Codex.dmg`（macOS arm64）
  - `https://persistent.oaistatic.com/codex-app-prod/Codex-latest-x64.dmg`（macOS x64）
  - `https://get.microsoft.com/installer/download/9PLM9XGG6VKS?cid=website_cta_psi`（Windows）
