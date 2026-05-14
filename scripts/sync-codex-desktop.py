#!/usr/bin/env python3
"""
Sync installer files from fixed direct URLs.

Priority:
1) SOURCE_FILE_URLS / --source-file-urls  (OS別など複数)
2) SOURCE_FILE_URL / --file-url (従来互換)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


USER_AGENT = "codex-desktop-sync/1.0"


def _build_headers(token: Optional[str], accept: Optional[str] = None) -> Dict[str, str]:
    headers: Dict[str, str] = {"User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if accept:
        headers["Accept"] = accept
    return headers


def _http_open(
    url: str,
    token: Optional[str] = None,
    method: str = "GET",
    accept: Optional[str] = None,
):
    req = urllib.request.Request(
        url,
        headers=_build_headers(token=token, accept=accept),
        method=method,
    )
    return urllib.request.urlopen(req, timeout=180)


def _head_metadata(url: str, token: Optional[str] = None) -> Dict[str, Optional[str]]:
    try:
        with _http_open(url, token=token, method="HEAD", accept="*/*") as resp:
            return {
                "etag": resp.headers.get("ETag"),
                "last_modified": resp.headers.get("Last-Modified"),
                "content_type": resp.headers.get("Content-Type"),
                "content_length": resp.headers.get("Content-Length"),
            }
    except Exception:
        # Some CDNs do not allow HEAD.
        return {
            "etag": None,
            "last_modified": None,
            "content_type": None,
            "content_length": None,
        }


def _parse_disposition_filename(content_disposition: Optional[str]) -> Optional[str]:
    if not content_disposition:
        return None
    m = re.search(
        r"filename\*=\s*UTF-8''([^;]+)",
        content_disposition,
        flags=re.IGNORECASE,
    )
    if m:
        return urllib.parse.unquote(m.group(1).strip().strip("\""))

    m = re.search(r"filename=\"([^\"]+)\"", content_disposition, flags=re.IGNORECASE)
    if m:
        return m.group(1)

    m = re.search(r"filename=([^;\\s]+)", content_disposition, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip().strip("'\"")
    return None


def _filename_from_header_or_url(
    response: Optional[urllib.request.addinfourl],
    url: str,
) -> str:
    if response is not None:
        header_name = _parse_disposition_filename(response.headers.get("Content-Disposition"))
        if header_name:
            return header_name

    path = urllib.parse.urlparse(url).path
    name = Path(urllib.parse.unquote(path)).name
    if name:
        return name
    return ""


def _download_file(url: str, out_path: Path, token: Optional[str] = None) -> Dict[str, Optional[str]]:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with _http_open(url, token=token, accept="application/octet-stream") as resp:
        filename = _filename_from_header_or_url(resp, url)
        with out_path.open("wb") as fp:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                fp.write(chunk)
        return {
            "content_type": resp.headers.get("Content-Type"),
            "content_length": resp.headers.get("Content-Length"),
            "etag": resp.headers.get("ETag"),
            "last_modified": resp.headers.get("Last-Modified"),
            "filename": filename,
        }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-.")
    return slug or "source"


def _load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


def _save_state(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
        fp.write("\n")


def _build_output_path(
    url: str,
    download_root: str,
    output_name: Optional[str],
    entry_key: Optional[str],
) -> Path:
    parsed = urllib.parse.urlparse(url)
    if entry_key:
        out_dir = Path(download_root) / _slugify(entry_key)
    else:
        source_slug = _slugify(f"{parsed.netloc}{parsed.path}")
        out_dir = Path(download_root) / source_slug

    out_dir.mkdir(parents=True, exist_ok=True)

    if output_name:
        return out_dir / Path(output_name).name

    inferred = Path(urllib.parse.unquote(parsed.path)).name
    if inferred:
        return out_dir / Path(inferred).name
    return out_dir / "installer"


def _normalize_source_entries(
    raw_urls: Optional[str],
    single_url: Optional[str],
    single_output: Optional[str],
) -> List[Dict[str, str]]:
    entries: List[Dict[str, str]] = []

    if raw_urls:
        parsed_ok = False
        try:
            obj = json.loads(raw_urls)
            parsed_ok = True
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if isinstance(value, str):
                        entry = {"key": str(key), "url": value}
                    elif isinstance(value, dict):
                        if not value.get("url"):
                            raise ValueError(f"SOURCE_FILE_URLS entry '{key}' is missing url")
                        entry = {
                            "key": str(key),
                            "url": value["url"],
                        }
                        if value.get("output_name"):
                            entry["output_name"] = str(value["output_name"])
                    else:
                        raise ValueError(f"SOURCE_FILE_URLS entry '{key}' has invalid format")
                    entries.append(entry)
            elif isinstance(obj, list):
                for i, item in enumerate(obj, start=1):
                    if isinstance(item, str):
                        if "=" in item:
                            key, url = item.split("=", 1)
                        else:
                            key = f"source-{i}"
                            url = item
                        entry = {"key": key.strip(), "url": url.strip()}
                        entries.append(entry)
                    elif isinstance(item, dict):
                        url = item.get("url")
                        if not url:
                            raise ValueError(f"SOURCE_FILE_URLS list item #{i} missing url")
                        key = item.get("key") or item.get("os") or item.get("platform") or f"source-{i}"
                        entry = {"key": str(key), "url": str(url)}
                        if item.get("output_name"):
                            entry["output_name"] = str(item["output_name"])
                        entries.append(entry)
                    else:
                        raise ValueError(f"SOURCE_FILE_URLS list item #{i} has invalid format")
            else:
                raise ValueError("SOURCE_FILE_URLS must be a JSON object or array")
        except json.JSONDecodeError:
            if parsed_ok:
                raise
            # Fallback: newline list
            for line_no, raw_line in enumerate(raw_urls.splitlines(), start=1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, url = line.split("=", 1)
                else:
                    raise ValueError(
                        f"SOURCE_FILE_URLS line {line_no} is invalid. Use key=url or JSON"
                    )
                entries.append({"key": key.strip(), "url": url.strip()})

    if not entries and single_url:
        entry: Dict[str, str] = {
            "key": "",
            "url": single_url,
        }
        if single_output:
            entry["output_name"] = single_output
        entries.append(entry)

    if not entries:
        raise ValueError("No source URL configured.")

    # preserve only strings and remove empty entries
    normalized = []
    for entry in entries:
        key = (entry.get("key") or "").strip()
        url = (entry.get("url") or "").strip()
        if not key or not url:
            continue
        normalized.append({"key": key, "url": url, "output_name": entry.get("output_name", "")})
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download installer files from fixed direct URLs."
    )
    parser.add_argument(
        "--source-file-urls",
        default=os.getenv("SOURCE_FILE_URLS"),
        help="Direct installer URLs in JSON (recommended)",
    )
    parser.add_argument(
        "--file-url",
        default=os.getenv("SOURCE_FILE_URL"),
        help="Backward compatible single direct URL mode",
    )
    parser.add_argument(
        "--output-name",
        default=os.getenv("OUTPUT_NAME"),
        help="Optional output filename for single URL mode only",
    )
    parser.add_argument(
        "--download-root",
        default=os.getenv("DOWNLOAD_ROOT", "downloads"),
        help="Directory to store downloaded files",
    )
    parser.add_argument(
        "--state-path",
        default=os.getenv("STATE_PATH", "downloads/codex-desktop-sync-state.json"),
        help="Path to metadata file",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Always re-download even if metadata fingerprint has not changed",
    )
    args = parser.parse_args()

    token = os.getenv("SOURCE_TOKEN")
    entries = _normalize_source_entries(args.source_file_urls, args.file_url, args.output_name)
    if not entries:
        raise SystemExit("No valid SOURCE_FILE_URLS / SOURCE_FILE_URL was provided.")

    prev_state = _load_state(Path(args.state_path))
    prev_entries = prev_state.get("entries", {}) if isinstance(prev_state.get("entries"), dict) else {}
    if not prev_entries and prev_state.get("mode") == "fixed_url":
        prev_entries = {
            "": {
                "fingerprint": prev_state.get("fingerprint"),
                "download_path": prev_state.get("download_path"),
            }
        }

    results: List[Dict[str, Any]] = []
    changed = False
    state_entries: Dict[str, Dict[str, Any]] = {}

    for item in entries:
        key = item["key"]
        url = item["url"]
        output_name = item.get("output_name") or None
        out_path = _build_output_path(url, args.download_root, output_name, key)
        head_meta = _head_metadata(url, token=token)
        fingerprint = (
            f"url={url}|"
            f"etag={head_meta.get('etag')}|"
            f"last_modified={head_meta.get('last_modified')}|"
            f"size={head_meta.get('content_length')}"
        )

        prev = prev_entries.get(key, {})
        if (
            not args.force
            and prev.get("fingerprint") == fingerprint
            and out_path.exists()
        ):
            results.append(
                {
                    "status": "no_change",
                    "key": key,
                    "url": url,
                    "path": str(out_path),
                    "fingerprint": fingerprint,
                }
            )
            state_entries[key] = prev
            continue

        download_meta = _download_file(url, out_path, token=token)
        digest = _sha256(out_path)
        if not output_name and download_meta.get("filename"):
            resolved = out_path.with_name(Path(download_meta["filename"]).name)
            if resolved.name != out_path.name:
                out_path.replace(resolved)
                out_path = resolved

        entry_state = {
            "key": key,
            "url": url,
            "fingerprint": fingerprint,
            "download_path": str(out_path),
            "content_type": download_meta.get("content_type") or head_meta.get("content_type"),
            "asset_size": int(
                (download_meta.get("content_length") or head_meta.get("content_length") or -1)
            ),
            "etag": download_meta.get("etag") or head_meta.get("etag"),
            "last_modified": download_meta.get("last_modified") or head_meta.get("last_modified"),
            "sha256": digest,
        }
        state_entries[key] = entry_state
        changed = True
        results.append(
            {
                "status": "synced",
                "key": key,
                "url": url,
                "path": str(out_path),
                "sha256": digest,
            }
        )

    state = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "fixed_urls",
        "entries": state_entries,
    }
    _save_state(Path(args.state_path), state)

    if changed:
        print(json.dumps({"status": "synced", "results": results}, ensure_ascii=False))
    else:
        print(json.dumps({"status": "no_change", "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
