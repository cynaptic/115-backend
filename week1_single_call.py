"""Week 1 - 透過 NVIDIA 的 OpenAI 相容 API 呼叫一次聊天模型。

使用方式：
    pip install -r requirements.txt
    export NVIDIA_API_KEY="你的金鑰"  # Windows PowerShell: $env:NVIDIA_API_KEY="你的金鑰"
    python week1_single_call.py

注意：不要把 API key 寫進程式碼或提交到 GitHub。
"""

import json
import os
import sys

import requests

API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "minimaxai/minimax-m3.1-flash"


def call_model(messages):
    """送出一次 POST request，列印 HTTP status 和 JSON response。"""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        print("錯誤：尚未設定 NVIDIA_API_KEY 環境變數。", file=sys.stderr)
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 512,
        "temperature": 1,
        "top_p": 0.95,
    }

    try:
        response = requests.post(
            API_URL,
            headers=headers,
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:
        print(f"連線失敗：{type(exc).__name__}", file=sys.stderr)
        return None

    # HTTP Response Status Code (例如 200、400、401)
    print("status:", response.status_code)

    try:
        data = response.json()
    except ValueError:
        print("error: 伺服器回應不是合法的 JSON。", file=sys.stderr)
        return None

    # HTTP Response Body
    print(json.dumps(data, ensure_ascii=False, indent=2))

    if response.ok:
        # 模型文字在 choices[0].message.content
        try:
            reply = data["choices"][0]["message"]["content"]
            print("reply:", reply)
        except (KeyError, IndexError, TypeError):
            print("error: 回應中找不到 choices[0].message.content。", file=sys.stderr)
    else:
        # 認證、model 名稱或欄位錯誤，通常會回傳 4xx 與 error
        print("error:", json.dumps(data.get("error", data), ensure_ascii=False))

    return data


if __name__ == "__main__":
    call_model([{"role": "user", "content": "用一句話說明什麼是 HTTP"}])
