# book-article-gen — Claude 工作手冊

這個專案用 Claude Agent SDK 跑一個「編輯部」多 agent pipeline：使用者給一個主題，pipeline 產出 N 個版本的長文 + 可選的社群短文。書庫是樊登讀書的解讀 transcript（不是書本原文）。

人寫的詳細說明：[readme.html](readme.html) / [readme.pdf](readme.pdf)。這份檔案專門給 Claude — 進來時先讀這個，就能立刻幫使用者「**跑**」或「**改**」。

---

## 你最常被叫來做的兩件事

### A. 幫使用者「跑出文章」

使用者說想產文時 — **不要直接丟指令給他**。改成：**一題一題問清楚需求 → 幫他寫好 [config.toml](config.toml) → 告訴他直接跑 `uv run python main.py`**（不帶任何參數，因為 config 都填好了）。

#### Step 1：問問題（一次一題，等使用者回答再問下一題）

按順序問下面這些。使用者答「不知道 / 你決定 / 隨便」就用 default 跳過。

1. **主題是什麼？**（會寫進 `[output] topic`）
2. **要產幾個版本？**（會寫進 `[output] versions`，default 3）
3. **每版想指定風格 mode 嗎？還是讓總編輯自挑？**
   - 列出 5 種 mode 給使用者選：
     - `story` — 情境長、角色入肉、生活細節密（建議 3000–5000 字）
     - `philosophical` — 短句排比、反問層疊、典故類比（建議 3000–5000 字）
     - `wisdom-anchor` — 單一典故/誓詞/書本概念當主軸（建議 3000–5000 字）
     - `actionable` — 故事鋪陳後接步驟、清單、可執行建議（建議 3000–5000 字）
     - `thread` — 台灣 Threads 爆文，第一人稱口語自白（建議 ~150 字、上限 500）
   - 使用者可以「全部讓總編輯挑」、「指定前幾版、剩下總編挑」、或「每版都指定」
4. **每版目標字數？**（會寫進 `[[versions]] length`；`thread` 不要照搬幾千字，建議 ~150）
5. **要不要產社群短文？**（`[social_post] enabled`）
   - 若是，問**平台**（`threads` / `ig` / `fb` / `general`）和**字數**（default 300）
6. **要不要開 AI 味審查？**（`[review] enabled`）
   - 若是，問**幾輪**（0–5，default 1；3 輪以上會 diminishing return）

問完前**不要動 config.toml**。問題之間使用者改主意可以回頭改。

#### Step 2：寫 config.toml

依答案產出 [config.toml](config.toml)（從 [config.toml.example](config.toml.example) 為基底）：

- `[output] topic` 填使用者給的主題
- `[output] versions` 填版本數
- `[[versions]]` 條目按使用者指定填（**數量 ≤ versions**；少於 versions 表示剩下的版本由總編輯自挑）
- `[social_post]` 和 `[review]` 按答案填
- 沒被問到的欄位（retrieval / character / models 等）不要動，沿用 default

寫完用 Read 給使用者看一眼確認。

#### Step 3：告訴使用者跑

```bash
uv run python main.py
```

不用帶 `--topic` / `--versions` 任何參數，因為 config 都填好了。產出在 `output/<slug>/output_{1..N}.txt`。

提醒使用者確認 `ANTHROPIC_API_KEY` 環境變數有設。

#### 例外：使用者堅持「我就要直接跑、不要問」

那就退回到原本的 CLI 模式：

```bash
uv run python main.py --topic "主題" --versions 3
uv run python main.py --input example/某主題/input.txt --versions 3 --slug 某主題
```

### B. 幫使用者「改行為」

使用者說「我想讓文章更 X」或「能不能加一種風格」之類 — 改的位置依需求對應：

| 使用者想改什麼 | 改哪裡 |
|---|---|
| 某個 agent 的判斷邏輯、輸出格式、鐵律 | [prompts/](prompts/) 對應 `.md`（`orchestrator` / `writer` / `hotspot` / `pain_point` / `character` / `book` / `social`）|
| **寫稿的風格細節**（5 種 mode 怎麼寫、共通要求、key_passage 怎麼引用） | [prompts/writer.md](prompts/writer.md) — 寫稿全部在 writer，不在 orchestrator |
| 加一種寫作風格（narrative_mode） | [prompts/writer.md](prompts/writer.md) Step 2 加 mode 寫作指引 + [prompts/orchestrator.md](prompts/orchestrator.md) Step 2 的 mode 列表加新名字 + [config.py](config.py) `VALID_STYLES` |
| 字數、版本數、style 預先指定 | [config.toml](config.toml) `[output]` / `[[versions]]` |
| 輸出資料夾位置或 slug | [config.toml](config.toml) `[output] dir` / `[output] slug`（CLI `--output` / `--slug` 仍可覆蓋）|
| 預設 topic（讓 `uv run main.py` 不用帶參數）| [config.toml](config.toml) `[output] topic`（CLI `--topic` / `--input` 仍可覆蓋）|
| 改 model 配置（省成本 or 提品質） | [config.toml](config.toml) `[models]` |
| 角色 agent 產幾個候選人 | [config.toml](config.toml) `[character] count` |
| 書庫檢索行為（每篇幾本書、每本幾段） | [config.toml](config.toml) `[retrieval]` |
| 社群短文開關 / 平台 / 長度 | [config.toml](config.toml) `[social_post]` |
| AI 味審查開關 / 迭代次數 | [config.toml](config.toml) `[review]`（預設關閉。開啟後每篇寫完跑 N 輪「審查→改寫」）|
| 加新書到書庫 | 把 `<id>_<書名>/` 放進 [book_data/](book_data/)（含 `<id>_<書名>.json` + `mindmap.json`），然後跑 `uv run python scripts/build_index.py` 重建 [index/book_index.json](index/) 與 chroma DB |
| 改 passage_search 行為 | [agents/book_tools.py](agents/book_tools.py) |
| 改 pipeline orchestration / SDK 配置 | [pipeline.py](pipeline.py) |
| 改 config schema / 預設值 | [config.py](config.py) |

---

## 系統結構速覽

```
main.py            CLI 入口（click）
pipeline.py        Claude Agent SDK orchestration、in-process MCP server 註冊
config.py          config.toml schema + load_config()
agents/            subagent 定義 + passage_search MCP tool
prompts/           5 個 agent 的 system prompt（總編輯 + 4 個專家）
book_data/         書庫原始資料（樊登 transcript JSON + mindmap）
index/             book_index.json（精簡 mindmap pack）+ chroma 向量庫
scripts/           build_index.py（rebuild index/）
example/AA制/      風格範例（few-shot）
output/            產出位置
```

**Pipeline 流程**：
1. 研究階段（依序）：`熱點` → `卡點` → `角色` → `書籍`
2. 規劃階段：`總編輯` 自己內部規劃 N 版差異化（角色 / 書 / mode / angle_hint / avoid）
3. 寫稿階段：總編輯**一回合內平行 fan-out N 個 `寫手` subagent**，每個寫手是獨立 session、寫一篇、自己 Write 到指定路徑
4. （可選）審查階段：如果 dispatch JSON 帶有 `review` 欄位，**寫手自己呼叫 `mcp__editor__ai_free_review` 工具**（不是 subagent），拿到審查報告後自己改寫並覆寫檔案。reviewer prompt 直接 copy 自 [editer_skill_set/ai-free-editor/SKILL.md](editer_skill_set/ai-free-editor/SKILL.md)，**不要改寫**
5. （可選）社群階段：如果 dispatch JSON 帶有 `social_post` 欄位，**寫手自己呼叫 `mcp__editor__social_rewrite` 工具** + Write _social.txt — 不經過總編輯

**重點**：
- 總編輯**不寫稿**，只規劃和派發。避免 N 篇連續寫造成 context 累積/版本同質化
- 寫手是「一版的完整 owner」：長文 + 審查改寫 + 社群 一起出。N 版完全獨立，平行執行
- 寫稿在獨立 subagent session，context 天然乾淨
- **審查 / 社群是 MCP 工具，不是 subagent**：Claude Agent SDK 限制 subagent 不能再派 subagent（"Task is not available inside subagents"），所以這兩個流程用 in-process MCP tool 實作 — 寫手呼叫工具就像呼叫普通 function，工具內部各跑一個獨立的 `query()`（在 [agents/editor_tools.py](agents/editor_tools.py)）。架構上仍是「寫手 owner 自己這版」

5 種 narrative_mode：`story` / `philosophical` / `wisdom-anchor` / `actionable` / `thread`。
其中 `thread` 是台灣 Threads 爆文：超短（~150 字，上限 500）、第一人稱、必須有爭議性。

---

## 改 prompt 時的注意事項

- **書籍 agent 的鐵律**（[prompts/book.md](prompts/book.md) 開頭）：只能引用 `index/book_index.json` 內存在的書 — 改 prompt 時不要破壞這條，會讓 agent 開始幻想書名
- **寫手的「書要真的引用」規則**（[prompts/writer.md](prompts/writer.md) Step 3）：書庫是樊登 transcript，引用時要用「樊登在解讀《書名》時說……」這類轉述包裝。`thread` 模式因字數太短是例外
- **總編輯 dispatch 寫手時要塞完整資料**（[prompts/orchestrator.md](prompts/orchestrator.md) Step 3）：character / book / hotspot / pain_point 都要傳完整物件，因為寫手是獨立 session 看不到上下文
- **5 種 mode 的 style key**：`story` 在 prompt 內叫 `story-heavy`，config 內叫 `story` — 不要混淆
- 改 prompt 後不用重建任何東西，下一次 `uv run python main.py` 就會讀新版

## 改 config 時的注意事項

- `[[versions]]` 條目數 ≤ `versions`。少於 N 表示「前 k 版照 spec、剩下總編輯自挑」
- `length` 是目標字數；`length_tolerance` 是 ±誤差比例（0.15 = ±15%）
- `thread` 預設 length 應該設 ~150（上限 500），不要照搬其他 mode 的數千字
- `social_post.platform = "fb"` 時容忍度自動放寬到 +25%

## 重建索引

只在動 [book_data/](book_data/) 時才需要：

```bash
uv run python scripts/build_index.py
```

會重建 [index/book_index.json](index/) 與 chroma DB。改 prompt / config 不需要。
