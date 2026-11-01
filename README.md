# Medi-Agent MCP

> 淡江大學電機工程學系 人工智慧機器人碩士班 碩士論文（2026）
> **基於 RAG 與 MCP 協定之混合式醫療對話系統**

> [!WARNING]
> 本專案為**學術研究原型**，不提供醫療建議，**不可用於臨床診斷或實際用藥判斷**。用藥問題請諮詢醫師或藥師。

## 研究動機

通用大型語言模型在醫療問答上常出現幻覺，且無法辨識台灣在地藥品名稱（如「斯斯」）。本研究結合靜態知識檢索（RAG）與即時工具呼叫（MCP），讓回答可溯源、能偵測高風險用藥情境。

## 系統架構

```
LINE Bot → n8n（流程編排）→ Gemini 2.5 Flash
                ├─ RAG：Pinecone 向量資料庫（MedQuAD，15,912 筆醫學問答）
                ├─ MCP：openFDA 官方仿單 API、KingNet 台灣藥品資訊
                └─ 雙層安全護欄（Dual-Guardrails & Code-Supervised）
```

## 主要結果

| 指標 | Medi-Agent MCP | GPT-4o |
|---|---|---|
| 危險偵測率 | **87.5%** | 37.5% |
| 答案可溯源率 | **93.3%** | 3.3% |

- 消融實驗 n = 120（30 題 × 4 個系統版本），混合架構是唯一在四種情境下都沒有系統性失能的版本
- 8 組高危藥物交互作用壓力測試全數攔截

## 目錄

| 路徑 | 內容 |
|---|---|
| `mcp-server/` | 藥物交互作用 MCP server（Node.js / Express / SSE） |
| `workflows/` | n8n workflow 匯出檔（金鑰已移除） |
| `prompts/` | 提示詞迭代版本 |
| `analysis/` | MedQuAD 上傳 Pinecone、熱力圖產生 script |
| `results/figures/` | 論文圖表 |
| `evaluation/` | 30 題評測集 |
| `deploy/` | n8n docker-compose |

## 執行 MCP server

```bash
cd mcp-server
npm install
node index.js   # http://localhost:3001/sse
```

其他服務所需的環境變數請見 `.env.example`。

## 資料來源與使用說明

- **MedQuAD**：Ben Abacha & Demner-Fushman (2019)，[原始資料集](https://github.com/abachaa/MedQuAD)。本 repo 不含資料集本身。
- **openFDA**：美國 FDA 公開 API。
- **KingNet 國家網路醫藥**：系統僅在使用者提問時即時查詢單筆藥品，每筆查詢間隔 5 秒，不批量擷取、不儲存或重新散布網站內容。網站內容著作權屬 KingNet 所有，若網站方有疑慮請來信，將配合移除。
- 本 repo **不包含**任何使用者對話、個人資料、API 金鑰或向量資料。

## 授權

程式碼採 [MIT License](LICENSE)。
