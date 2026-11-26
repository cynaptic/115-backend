"""Week 2 - 工具描述與分派：模型提出，程式執行。

一次工具呼叫被拆成兩筆 API 交易：
    1. 第一次請求帶 tools，模型回傳 tool_calls（建議，不是答案）。
    2. 程式依 name/arguments 執行工具，把結果以 role="tool" 回填 messages。
    3. 第二次請求不帶 tools，模型只能依 tool result 產出最終 content。

使用方式：
    pip install -r requirements.txt
    export NVIDIA_API_KEY="你的金鑰"      # Windows PowerShell: $env:NVIDIA_API_KEY="你的金鑰"
    python week2_tool_dispatch.py
    python week2_tool_dispatch.py "用 http_get 抓 https://www.python.org，用一句話說明"

注意：不要把 API key 寫進程式碼或提交到 GitHub。
"""

import json
import os
import sys

import requests

# Windows 主控台預設編碼（cp950/cp1252）可能無法輸出中文，強制用 UTF-8 並把無法編碼的
# 字元換成 ?，避免程式在印 log 時就掛掉。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
MODEL = "minimaxai/minimax-m3.1-flash"
DEFAULT_TASK = "用 http_get 抓取 https://example.com，然後用一句話說明你看到什麼。"

# 工具描述 (tool schema)：模型不知道你的程式能做什麼，除非你寫進 Request 的 tools。
# 三個欄位各有讀者：type 給 API、name 給模型選工具、description 給模型判斷時機、
# parameters 給模型產生 arguments。
HTTP_GET_TOOL = {
    "type": "function",
    "function": {
        "name": "http_get",
        "description": "Fetch a URL with HTTP GET. Return status code and a short body summary.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Absolute http(s) URL to fetch.",
                }
            },
            "required": ["url"],
        },
    },
}


def get_api_key():
    """從環境變數讀金鑰，缺席時直接說清楚少了什麼。"""
    api_key = os.environ.get("NVIDIA_API_KEY")
    if not api_key:
        raise SystemExit(
            "錯誤：尚未設定 NVIDIA_API_KEY 環境變數。\n"
            '  PowerShell: $env:NVIDIA_API_KEY="你的金鑰"'
        )
    return api_key


def call_model(messages, tools=None):
    """送出一次 POST /chat/completions，回傳 choices[0].message。

    tools=None 時 Request Body 不帶 tools（第二次呼叫就是用這種方式不讓模型再提工具）。
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": 512,
        "temperature": 1,
        "top_p": 0.95,
    }
    if tools is not None:
        payload["tools"] = tools

    try:
        response = requests.post(
            API_URL,
            headers={
                "Authorization": f"Bearer {get_api_key()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
    except requests.RequestException as exc:
        print(f"連線失敗：{type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1)

    # HTTP Response Status Code
    print("status:", response.status_code)

    try:
        data = response.json()
    except ValueError:
        print("error: 伺服器回應不是合法的 JSON。", file=sys.stderr)
        raise SystemExit(1)

    if not response.ok:
        # 401 = 認證、400/404 = model 名稱或欄位；先看 status 再讀 body。
        print("error:", json.dumps(data.get("error", data), ensure_ascii=False))
        raise SystemExit(1)

    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        print("error: 回應中找不到 choices[0].message。", file=sys.stderr)
        raise SystemExit(1)


def http_get(url):
    """工具本體：真的發出 HTTP GET，回傳可序列化的結果。"""
    response = requests.get(url, timeout=10)
    return {
        "status_code": response.status_code,
        "body_summary": response.text[:120],
    }


def dispatch(name, arguments):
    """依模型建議的 name 與 arguments 執行工具。

    arguments 是 JSON 字串（不是 dict），要先 json.loads 才能拿到 url。
    """
    if name != "http_get":
        raise ValueError(f"unknown tool: {name}")
    args = json.loads(arguments)
    return http_get(args["url"])


def run(task):
    messages = [{"role": "user", "content": task}]

    # 第一次 API 交易：帶 tools，取得 tool_calls
    print("[1] 第一次 API 請求（帶 tools）")
    first = call_model(messages, tools=[HTTP_GET_TOOL])
    print("tool_calls:", json.dumps(first.get("tool_calls"), ensure_ascii=False, indent=2))
    if not first.get("tool_calls"):
        raise SystemExit("沒有拿到 tool_calls；先檢查工具描述與 user message。")

    # 把含 tool_calls 的 assistant 訊息 append 回去，順序不能顛倒
    messages.append(first)

    # 工具執行：模型建議 vs 程式實際執行
    print("[2] 程式分派與執行")
    for call in first["tool_calls"]:
        print("模型建議:", call["function"]["arguments"])
        result = dispatch(call["function"]["name"], call["function"]["arguments"])
        print("程式執行:", json.dumps(result, ensure_ascii=False))
        # tool_call_id 必須等於上一步的 id，模型才知道這筆結果對應哪個建議
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call["id"],
                "content": json.dumps(result, ensure_ascii=False),
            }
        )

    # 第二次 API 交易：不帶 tools，取得最終 content
    print("[3] 第二次 API 請求（不帶 tools）")
    final = call_model(messages)
    print("reply:", final.get("content"))
    return final.get("content")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TASK)
