"""Claude API（Messages API）を標準ライブラリだけで呼ぶ。

公式SDKも外部ライブラリなので使わず、urllib で直接 HTTP を送る（フォルダごとコピーで動かすため）。
APIキーは環境変数 ANTHROPIC_API_KEY、またはプロジェクト直下の .env から読む。
"""

import json
import os
import time
import urllib.error
import urllib.request

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
# 安全分類器が応答を断ったとき、Anthropic 推奨の別モデルでサーバー側が自動でやり直す（ベータ）
FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_MODEL = "claude-opus-5-5"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ClaudeError(RuntimeError):
    """Claude API の呼び出しに失敗した（利用者に見せられる日本語のメッセージを持つ）。"""


def api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    path = os.path.join(ROOT, ".env")
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                name, _, value = line.strip().partition("=")
                if name.strip() == "ANTHROPIC_API_KEY" and value.strip():
                    return value.strip().strip('"').strip("'")
    raise ClaudeError("APIキーがありません。tolmon フォルダの .env に ANTHROPIC_API_KEY=… を書いてください")


def _post(body, timeout):
    req = urllib.request.Request(
        API_URL, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json", "x-api-key": api_key(),
                 "anthropic-version": API_VERSION, "anthropic-beta": FALLBACK_BETA})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.loads(res.read().decode("utf-8"))


def _error_message(e):
    try:
        detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
    except (ValueError, OSError):
        detail = ""
    hints = {401: "APIキーが正しくありません（.env を確認してください）",
             403: "このAPIキーでは使えません（権限を確認してください）",
             404: "モデル名が正しくありません",
             413: "ファイルが大きすぎます",
             429: "利用が集中しています。少し待ってからやり直してください"}
    head = hints.get(e.code, f"Claude API がエラーを返しました（{e.code}）")
    return f"{head}：{detail}" if detail else head


def call(system, content, schema, model=DEFAULT_MODEL, effort="high", max_tokens=16000, timeout=600):
    """Claude を1回呼び、schema（JSONスキーマ）に沿った結果を dict で返す。

    content はユーザーメッセージの中身（文書・画像・テキストのブロックの並び）。
    戻り値は (結果の dict, 使用量などの情報 dict)。
    """
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": content}],
        # Opus 5.5 は考える深さを effort で決める（thinking の指定は不要）。結果は JSON スキーマで受け取る
        "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        "fallbacks": "default",
    }
    started = time.time()
    last = None
    for attempt in range(3):
        try:
            res = _post(body, timeout)
            break
        except urllib.error.HTTPError as e:
            # 混雑（429）とサーバー側の不調（5xx）だけ、少し待ってやり直す
            if e.code in (429, 500, 502, 503, 529) and attempt < 2:
                last = e
                time.sleep(3 * (attempt + 1))
                continue
            raise ClaudeError(_error_message(e)) from e
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            raise ClaudeError(f"Claude API につながりません（インターネット接続を確認してください）：{e}") from e
    else:
        raise ClaudeError(_error_message(last))

    stop = res.get("stop_reason")
    if stop == "refusal":
        raise ClaudeError("Claude がこの依頼を断りました（安全上の理由）。別の帳票で試してください")
    if stop == "max_tokens":
        raise ClaudeError("結果が長すぎて途中で切れました。問診票を1ページずつに分けて試してください")
    text = "".join(b.get("text", "") for b in res.get("content", []) if b.get("type") == "text")
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ClaudeError("Claude の返事を読み取れませんでした（JSONではありません）") from e
    usage = res.get("usage", {})
    info = {"model": res.get("model"), "seconds": round(time.time() - started, 1),
            "input_tokens": usage.get("input_tokens"), "output_tokens": usage.get("output_tokens")}
    return data, info
