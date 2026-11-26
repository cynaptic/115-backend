# Week 2 作業：一次完整 tool-use 對話紀錄

- 端點：`POST https://integrate.api.nvidia.com/v1/chat/completions`
- Model：`minimaxai/minimax-m3.1-flash`
- 參數：`max_tokens: 512`、`temperature: 1`、`top_p: 0.95`
- 程式：`week2_tool_dispatch.py`
- 金鑰：從環境變數 `NVIDIA_API_KEY` 讀取，本紀錄未包含 `Authorization` header 或任何金鑰字串。
- 執行環境：Python 3.11.9 / requests 2.34.2，Windows 11

一次工具呼叫被拆成兩筆獨立的 HTTP 交易：第一筆帶 `tools` 取得 `tool_calls`，程式執行後把結果以 `role: "tool"` 回填，第二筆不帶 `tools` 取得最終 `content`。

---

## 1. 第一次 API 請求：帶 `tools`

Request Body（節錄，`tools` 只有一個工具）：

```json
{
  "model": "minimaxai/minimax-m3.1-flash",
  "messages": [
    {
      "role": "user",
      "content": "用 http_get 抓取 https://example.com，然後用一句話說明你看到什麼。"
    }
  ],
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "http_get",
        "description": "Fetch a URL with HTTP GET. Return status code and a short body summary.",
        "parameters": {
          "type": "object",
          "properties": {
            "url": {
              "type": "string",
              "description": "Absolute http(s) URL to fetch."
            }
          },
          "required": ["url"]
        }
      }
    }
  ],
  "max_tokens": 512,
  "temperature": 1,
  "top_p": 0.95
}
```

## 2. 第一次 API 回應：`status: 200`，拿到的是建議不是答案

```json
{
  "content": null,
  "refusal": null,
  "tool_calls": [
    {
      "id": "call-ce28ac8b-e7fe-44f4-a0d1-07bc8fc9960d",
      "type": "function",
      "function": {
        "name": "http_get",
        "arguments": "{\"url\":\"https://example.com\"}"
      }
    }
  ],
  "role": "assistant",
  "reasoning_content": "The user wants me to fetch https://example.com using http_get, then describe in one sentence what I see. Simple task. Let me call the tool."
}
```

`content` 是 `null`、`tool_calls` 有內容，代表模型這輪只提出呼叫建議，還沒回答問題。

注意 `arguments` 是 **JSON 字串**（`"{\"url\":\"https://example.com\"}"`），不是 dict；程式必須先 `json.loads` 才拿得到 `url`。

## 3. 程式執行工具（模型建議 vs 程式實際執行）

```
模型建議: {"url":"https://example.com"}
程式執行: {"status_code": 200, "body_summary": "<!doctype html><html lang=en><head><meta charset=utf-8><link rel=icon href=data:,<meta name=viewport content=\"width=dev"}
```

程式做的事：`dispatch(name, arguments)` → `json.loads(arguments)` → `requests.get(url, timeout=10)` → 只留前 120 字。真正的 HTTP 請求是 `http_get()` 裡的 `requests.get` 發出的，不是模型。

## 4. 第二次 API 請求：不帶 `tools`，`messages` 有三筆

```json
[
  {
    "role": "user",
    "content": "用 http_get 抓取 https://example.com，然後用一句話說明你看到什麼。"
  },
  {
    "role": "assistant",
    "content": null,
    "tool_calls": [
      {
        "id": "call-ce28ac8b-e7fe-44f4-a0d1-07bc8fc9960d",
        "type": "function",
        "function": {
          "name": "http_get",
          "arguments": "{\"url\":\"https://example.com\"}"
        }
      }
    ]
  },
  {
    "role": "tool",
    "tool_call_id": "call-ce28ac8b-e7fe-44f4-a0d1-07bc8fc9960d",
    "content": "{\"status_code\": 200, \"body_summary\": \"<!doctype html><html lang=en>...\"}"
  }
]
```

三個關鍵點：

1. 含 `tool_calls` 的 assistant 訊息要先 append，順序不能顛倒。
2. `tool_call_id` 必須等於第一次回應的 `id`（`call-ce28ac8b-...`），模型才知道這筆結果對應哪個建議。
3. 這一輪**不送 `tools`**：模型看不到工具，只能依 tool result 回答。

## 5. 第二次 API 回應：`status: 200`，最終 `content`

```json
{
  "content": "抓取成功（HTTP 200），我看到的是 example.com 的標準示範頁面，包含一個標題為「Example Domain」的主段落，說明此頁面可供網站文件中 illustrative 用途，並附上一個指向 iana.org 的「More information...」連結。",
  "refusal": null,
  "role": "assistant"
}
```

## 6. 四列對照表

| 步驟 | 模型建議 | 程式實際執行 |
| --- | --- | --- |
| 第一次 API 回應（`status: 200`） | `name: http_get`，`arguments: {"url":"https://example.com"}`，`id: call-ce28ac8b-e7fe-44f4-a0d1-07bc8fc9960d` | 尚未執行；只收到建議 |
| 工具執行 | 無 | `status_code: 200`；`body_summary` 為 `<!doctype html><html lang=en>...`（前 120 字） |
| 第二次 API 請求（`status: 200`） | 無 | `role: "tool"`，`tool_call_id` 與第一次的 `id` 相同 |
| 第二次 API 回應（`status: 200`） | 無 | `choices[0].message.content` = 「抓取成功（HTTP 200）...」 |

---

## 7. 過程中值得記錄的兩件事

### (a) 第一次執行時第二次呼叫回 503

第一次跑的時候第一筆是 200，第二筆失敗：

```
status: 503
error: {"message": "content safety screening is temporarily unavailable"}
```

回應不是 JSON 的 `choices`，而是服務端的錯誤物件。程式在 `resp.ok` 為 false 時印出 `error` 並中止，沒有把錯誤內容當成模型回答。重試後即恢復 200，屬服務端暫時性問題，不是 Request 內容錯誤。

### (b) 模型的回答超出程式回填的摘要範圍

回填的 `body_summary` 只有 120 字，結尾在 `width=dev`，並沒有頁面標題「Example Domain」或 `iana.org` 連結。但第二次回應卻說出這些內容——那是模型對 `example.com` 的既有印象，不是 tool result 給的觀察。

這正是「模型提出、程式執行」要分清楚的地方：能查證的只有 `status_code` 與 `body_summary`。若需要模型講頁面細節，程式就得回填更多內容，而不是讓模型自己補。

## 8. 自我檢查

**模型建議的 URL 在哪裡？**
在第一次回應的 `choices[0].message.tool_calls[0].function.arguments` 裡，值是 JSON 字串 `{"url":"https://example.com"}`，要先 `json.loads`。

**程式用哪個函式真的發出請求？**
`http_get()` 裡的 `requests.get(url, timeout=10)`；`dispatch()` 只負責依 `name` 選工具並解析參數。

**`tool_call_id` 對不上會發生什麼？**
模型無法把 tool result 對應到它提出的呼叫，API 會回 400（缺少對應的 tool call），或模型把它當成無關的使用者訊息而忽略，回覆品質下降。

**為什麼第二次呼叫不帶 `tools`？**
因為這一步只要求模型根據已知的觀察產出答案；不帶 `tools` 才能確保它不再提出新呼叫（若任務仍需多步，那是 Week 3 迴圈的事）。同時也讓「第二筆交易」的職責單純：只做彙整。
