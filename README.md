# Codex Desktop 自動同期（GitHub Releases）

このリポジトリは、固定URLの監視だけで Codex Desktop のインストーラーを取得し、  
**巨大バイナリは GitHub Releases のアセットとして配布**します。

- リポジトリ本体には `downloads/*` をコミットしない
- LFS は使わない
- 変更時のみリリースアセットを更新（`--clobber`）

## 運用方式

- `.github/workflows/sync-codex-desktop.yml` が `SOURCE_FILE_URLS` を監視
- 更新検出時は `downloads/<key>/` 配下の最新ファイルを `codex-desktop-latest` リリースへアップロード
- 変更なしならリリース更新を行わない

### 手順

1. URLを変更する場合: `.github/workflows/sync-codex-desktop.yml` の `SOURCE_FILE_URLS` を更新
2. 手動実行: GitHub Actions の `workflow_dispatch`
3. 定期実行: `0 * * * *`（UTC）

## `SOURCE_FILE_URLS` 例

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

`key` と `url` が必須。`output_name` は任意。

## リリース配布先

- リリース一覧: `https://github.com/<owner>/<repo>/releases`
- 固定タグ: `codex-desktop-latest`
- アセットは毎回同名で上書きされます（`gh release upload --clobber`）

## ローカル実行（確認用）

```bash
python3 scripts/sync-codex-desktop.py \
  --source-file-urls '{
    "macos-arm64": {
      "url": "https://persistent.oaistatic.com/codex-app-prod/Codex.dmg",
      "output_name": "Codex.dmg"
    }
  }' \
  --download-root downloads \
  --state-path downloads/codex-desktop-sync-state.json
```

`status` が `synced` のときのみ、GitHub Releases を更新します。
