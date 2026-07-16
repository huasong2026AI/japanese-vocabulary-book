import os
import json
import csv
import io
import base64
import uvicorn
from zhipuai import ZhipuAI  # 引入智谱官方SDK
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional
from pypdf import PdfReader

app = FastAPI(title="情境生词消灭器-安全生产版")

# ==========================================
# 1. 智谱 AI API Key 核心防护层（改用系统环境变量读取）
# ==========================================
ZHIPU_API_KEY = os.environ.get("ZHIPU_API_KEY")

if not ZHIPU_API_KEY:
    # 给出明确的本地/线上未配置提示，防止程序静默崩溃
    print("⚠️ 警告: 未检测到系统环境变量 ZHIPU_API_KEY，AI 功能将无法正常使用！")
    # 如果本地测试，也可以在此处临时写一个备用 Key，但切记不要提交到公开仓库
    ZHIPU_API_KEY = "YOUR_LOCAL_BACKUP_KEY_IF_NEEDED"

client_ai = ZhipuAI(api_key=ZHIPU_API_KEY)

# ==========================================
# 2. 本地持久化数据中心
# ==========================================
DB_FILE = "cards_db.json"

DEFAULT_CARDS = [
    {
        "id": 1, "word": "相棒", "furigana": "あいぼう",
        "meaning_ja": "一緒に仕事や行動をする大切なパートナーのこと。",
        "meaning_zh": "老搭档、死党、伙伴", "context_source": "日剧",
        "example_sentence": "お前は俺の最高の相棒だ。（你是我最好的搭档。）", "tags": "日剧", "status": "learning"
    },
    {
        "id": 2, "word": "一口", "furigana": "ひとくch",
        "meaning_ja": "食べ物や飲み物を、口の中に一度に入れる量。",
        "meaning_zh": "（吃/喝）一口", "context_source": "日常",
        "example_sentence": "これ、めちゃくちゃ美味しいから一口食べてみて！", "tags": "日常", "status": "learning"
    }
]

def load_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data
        except Exception as e:
            print(f"读取数据库文件失败，切换到默认数据: {str(e)}")
    
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CARDS, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"初始化数据库文件失败: {str(e)}")
    return DEFAULT_CARDS


def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"保存数据库失败: {str(e)}")


# 服务启动时一次性加载到内存
db_cards = load_db()


# ==========================================
# 3. 数据交互模型
# ==========================================
class CardItem(BaseModel):
    id: Optional[int] = None
    word: str
    furigana: str
    meaning_ja: Optional[str] = ""
    meaning_zh: str
    context_source: str
    example_sentence: str
    tags: str
    status: Optional[str] = "learning"


class AIRequest(BaseModel):
    word: str
    hint_sentence: Optional[str] = ""


class StatusUpdateRequest(BaseModel):
    status: str


# ==========================================
# 4. 后端路由与大模型交互
# ==========================================
@app.get("/api/cards")
def get_cards(tag: Optional[str] = None, filter_status: Optional[str] = "learning"):
    cards = db_cards
    if filter_status:
        cards = [c for c in cards if c.get("status", "learning") == filter_status]
    if tag and tag != "全部":
        cards = [c for c in cards if tag in c["tags"]]
    return cards[::-1]


@app.post("/api/cards")
def save_or_update_card(card: CardItem):
    global db_cards
    if not card.word or not card.meaning_zh:
        raise HTTPException(status_code=400, detail="生词和中文释义不能为空")

    if "日常" in card.tags or "生活" in card.tags:
        card.tags = "日常"
    elif "剧" in card.tags or "动漫" in card.tags:
        card.tags = "日剧"
    else:
        card.tags = "日常"

    if card.id is not None:
        for idx, item in enumerate(db_cards):
            if item["id"] == card.id:
                db_cards[idx] = card.dict()
                save_db(db_cards)
                return {"status": "success", "action": "updated"}
        raise HTTPException(status_code=404, detail="未找到对应的卡片")
    else:
        new_id = max([c["id"] for c in db_cards]) + 1 if db_cards else 1
        card_dict = card.dict()
        card_dict["id"] = new_id
        card_dict["status"] = "learning"
        db_cards.append(card_dict)
        save_db(db_cards)
        return {"status": "success", "action": "created"}


@app.delete("/api/cards/{card_id}")
def delete_card(card_id: int):
    global db_cards
    db_cards = [c for c in db_cards if c["id"] != card_id]
    save_db(db_cards)
    return {"status": "success"}


@app.post("/api/cards/{card_id}/status")
def update_card_status(card_id: int, payload: StatusUpdateRequest):
    for item in db_cards:
        if item["id"] == card_id:
            item["status"] = payload.status
            save_db(db_cards)
            return {"status": "success"}
    raise HTTPException(status_code=404, detail="未找到指定卡片")


@app.post("/api/ai-generate")
def ai_generate(payload: AIRequest):
    if not ZHIPU_API_KEY or ZHIPU_API_KEY.startswith("YOUR_LOCAL"):
        raise HTTPException(status_code=500, detail="检测到未配置智谱 API Key，请检查平台环境变量配置")
        
    if not payload.word:
        raise HTTPException(status_code=400, detail="生词不能为空")
    
    clean_word = payload.word.strip()
    
    prompt = (
        "你是一个精通中日双语的日语教学专家。请为以下日语生词进行解析。\n"
        f"待解析生词：{clean_word}\n"
        f"用户提供的情境提示：{payload.hint_sentence if payload.hint_sentence else '无'}\n\n"
        "请严格按照以下 JSON 格式返回数据，不要包含任何 markdown 标记，不要有任何废话：\n"
        "{\n"
        '  "furigana": "该生词的纯假名发音",\n'
        '  "meaning_zh": "该生词最准确的中文含义",\n'
        '  "meaning_ja": "【绝对只能使用纯日语！】用简单易懂、符合N4水平的日语来解释该词的意思。",\n'
        '  "context_source": "情境出处，如日剧台词、日常口语",\n'
        '  "example_sentence": "一句高频生活例句并附带括号中文翻译",\n'
        '  "tags": "只能从以下两个标签中选择一个填入：若属于动漫/日剧/台词填\'日剧\'，若是通用生活口语则填\'日常\'"\n'
        "}"
    )

    try:
        response = client_ai.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
        )
        raw_text = response.choices[0].message.content.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("\n", 1)[0]
        return json.loads(raw_text)
    except Exception as e:
        return {"error_type": "SDK_ERROR", "msg": f"大模型通讯失败: {str(e)}"}


@app.post("/api/insight/file-scan")
async def scan_file(file: UploadFile = File(...)):
    filename = file.filename.lower()
    extracted_text = ""

    if filename.endswith(".pdf"):
        try:
            pdf_bytes = await file.read()
            reader = PdfReader(io.BytesIO(pdf_bytes))
            for page in reader.pages[:5]:
                extracted_text += page.extract_text() or ""
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"PDF文本解析失败: {str(e)}")

    elif filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        try:
            image_bytes = await file.read()
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            response = client_ai.chat.completions.create(
                model="glm-4v-flash",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "请仔细辨认并提取出图片里的所有日语文本。不要任何解释说明，直接输出原文。"},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }],
                temperature=0.1
            )
            extracted_text = response.choices[0].message.content.strip()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"多模态视觉解析失败: {str(e)}")
    else:
        raise HTTPException(status_code=400, detail="暂不支持此格式文件")

    if not extracted_text.strip():
        return {"words": []}

    try:
        filter_prompt = (
            "请从以下文本中提取出适合N4-N3级别的核心词汇。\n"
            f"目标文本：\n{extracted_text}\n\n"
            "请直接返回一个纯JSON格式的字符串数组，例：[\"単語1\", \"単語2\"]"
        )
        res = client_ai.chat.completions.create(
            model="glm-4-flash",
            messages=[{"role": "user", "content": filter_prompt}],
            temperature=0.2
        )
        raw_arr = res.choices[0].message.content.strip()
        if raw_arr.startswith("```"):
            raw_arr = raw_arr.split("\n", 1)[1].rsplit("\n", 1)[0]
        return {"words": json.loads(raw_arr)}
    except:
        return {"words": [w.strip() for w in extracted_text.split() if w.strip()][:15]}


@app.get("/api/cards/export")
def export_excel():
    output = io.StringIO()
    output.write('\ufeff')
    writer = csv.writer(output)
    writer.writerow(["生词", "假名发音", "日文释义", "中文含义", "情境出处", "高频生活例句", "标签", "掌握状态"])
    for c in db_cards:
        status_zh = "已掌握" if c.get("status") == "mastered" else "正在复习"
        writer.writerow([c["word"], c["furigana"], c.get("meaning_ja", ""), c["meaning_zh"], c["context_source"],
                         c["example_sentence"], c["tags"], status_zh])
    output.seek(0)
    return StreamingResponse(io.BytesIO(output.getvalue().encode('utf-8')), media_type="text/csv",
                             headers={"Content-Disposition": "attachment; filename=my_japanese_cards.csv"})


@app.post("/api/cards/import")
async def import_excel(file: UploadFile = File(...)):
    global db_cards
    filename = file.filename.lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="请上传由本系统导出的 CSV 表格文件")
    try:
        contents = await file.read()
        text_content = contents.decode("utf-8-sig", errors="ignore")
        f_input = io.StringIO(text_content)
        reader = csv.reader(f_input)
        header = next(reader, None)
        if not header or header[0] != "生词" or header[1] != "假名发音":
            raise HTTPException(status_code=400, detail="表格表头不匹配，请使用标准的导出模板")
        
        new_id = max([c["id"] for c in db_cards]) + 1 if db_cards else 1
        imported_count = 0
        for row in reader:
            if not row or len(row) < 2:
                continue
            word = row[0].strip()
            furigana = row[1].strip()
            if not word or not furigana:
                continue
            meaning_ja = row[2].strip() if len(row) > 2 else ""
            meaning_zh = row[3].strip() if len(row) > 3 else ""
            context_source = row[4].strip() if len(row) > 4 else "导入"
            example_sentence = row[5].strip() if len(row) > 5 else ""
            tags = row[6].strip() if len(row) > 6 else "日常"
            status_zh = row[7].strip() if len(row) > 7 else "正在复习"
            status = "mastered" if status_zh == "已掌握" else "learning"
            
            db_cards.append({
                "id": new_id, "word": word, "furigana": furigana, "meaning_ja": meaning_ja,
                "meaning_zh": meaning_zh, "context_source": context_source,
                "example_sentence": example_sentence, "tags": tags, "status": status
            })
            new_id += 1
            imported_count += 1
        save_db(db_cards)
        return {"status": "success", "imported_count": imported_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导入解析失败: {str(e)}")


# ==========================================
# 5. 前端全景页面
# ==========================================
@app.get("/", response_class=HTMLResponse)
def index_page():
    return """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>情境生词消灭器</title>
        <style>
            :root {
                --forest-dark: #2d4a43; --forest-leaf: #4a7c6c; --forest-light: #f4f7f5;
                --wood-earth: #8ba89e; --text-main: #2c3e35; --text-sub: #60756c;
                --card-bg: #ffffff; --danger: #c96868; --success: #5ba37e;
            }
            body {
                background-color: var(--forest-light); color: var(--text-main);
                font-family: "Helvetica Neue", Arial, sans-serif; margin: 0; padding: 0; height: 100vh; display: flex; flex-direction: column;
            }
            header {
                background: var(--forest-dark); color: #ffffff; padding: 12px 24px; box-shadow: 0 2px 8px rgba(45,74,67,0.1);
                display: flex; justify-content: space-between; align-items: center; height: 36px;
            }
            .app-container { display: flex; flex: 1; overflow: hidden; padding: 16px; gap: 20px; box-sizing: border-box; }

            .left-panel {
                width: 480px; flex-shrink: 0; background: var(--card-bg); border-radius: 16px; padding: 16px; 
                box-shadow: 0 4px 14px rgba(45,74,67,0.05); display: flex; flex-direction: column; overflow-y: auto; border: 1px solid #e2e9e6;
            }
            .right-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

            .tree-hollow { background: #fdfaf4; border: 1px dashed var(--wood-earth); border-radius: 8px; padding: 10px; margin-bottom: 14px; }
            .word-pill { display: inline-block; background: #ebdcb9; color: #5a4525; padding: 4px 10px; border-radius: 14px; font-size: 12px; margin: 4px; cursor: pointer; font-weight: bold; transition: all 0.2s; }
            .word-pill:hover { background: var(--forest-leaf); color: white; }

            .control-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
            #tag-bar { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px; }
            .tag-btn { background: #e9f0ed; color: var(--text-sub); border: none; padding: 6px 12px; border-radius: 20px; font-size: 13px; cursor: pointer; white-space: nowrap; }
            .tag-btn.active { background: var(--forest-leaf); color: white; }

            .view-switch { background: #e2e9e6; padding: 4px; border-radius: 8px; display: flex; gap: 4px; }
            .switch-btn { border: none; background: transparent; padding: 4px 10px; font-size: 12px; border-radius: 6px; cursor: pointer; }
            .switch-btn.active { background: white; color: var(--forest-dark); font-weight: bold; }

            .cards-scroll-area { flex: 1; overflow-y: auto; display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 12px; padding-right: 4px; align-content: start; }

            .card-perspective { perspective: 1000px; width: 100%; min-height: 105px; position: relative; }
            .card-rotator { position: relative; width: 100%; height: 100%; min-height: 105px; transition: transform 0.4s ease; transform-style: preserve-3d; cursor: pointer; }
            .is-flipped { transform: rotateY(180deg); }

            .face-front, .face-back {
                backface-visibility: hidden; -webkit-backface-visibility: hidden; border-radius: 12px; padding: 12px; padding-right: 55px; box-sizing: border-box; width: 100%; height: 100%;
                background: var(--card-bg); border: 1px solid #e2e9e6; box-shadow: 0 2px 6px rgba(45,74,67,0.03);
            }
            .face-back { transform: rotateY(180deg); position: absolute; top: 0; left: 0; right: 0; bottom: 0; background: #fafcfb; border: 1px solid var(--wood-earth); overflow-y: auto; }

            h3 { margin: 0 0 12px 0; color: var(--forest-dark); font-size: 15px; border-bottom: 2px solid #e9f0ed; padding-bottom: 4px; }
            .form-group { margin-bottom: 8px; }
            .form-group label { display: block; font-size: 11px; color: var(--text-sub); font-weight: bold; margin-bottom: 2px; }
            .form-group input, .form-group textarea { width: 100%; padding: 6px 8px; background: #fafcfb; border: 1px solid #d3ded9; color: var(--text-main); border-radius: 6px; box-sizing: border-box; font-size: 13px; }
            .form-group input:focus, .form-group textarea:focus { border-color: var(--forest-leaf); outline: none; }

            .btn-action { width: 100%; border: none; padding: 8px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-bottom: 8px; }
            .btn-ai { background: var(--forest-leaf); color: white; }
            .btn-submit { background: var(--success); color: white; }

            .card-actions { position: absolute; right: 8px; top: 12px; z-index: 100; display: flex; gap: 4px; justify-content: flex-end; }
            .mini-btn { border: none; background: #e9f0ed; font-size: 11px; padding: 4px 6px; border-radius: 4px; cursor: pointer; color: var(--text-main); }
            .mini-btn:hover { background: var(--wood-earth); color: white; }
            .mini-btn.del { background: #fdf0f0; color: var(--danger); }
            .mini-btn.del:hover { background: var(--danger); color: white; }

            @media (max-width: 800px) {
                body { height: auto; overflow-y: auto; }
                .app-container { flex-direction: column; overflow: visible; height: auto; }
                .left-panel { width: 100%; height: auto; overflow: visible; box-sizing: border-box; margin-bottom: 20px; }
                .right-panel { width: 100%; height: auto; overflow: visible; }
                .cards-scroll-area { grid-template-columns: 1fr; overflow-y: visible; height: auto; }
            }
        </style>
    </head>
    <body>
        <header>
            <div style="font-weight: bold; font-size: 15px;">🍃 情境生词消灭器 <span style="font-size:11px; background: rgba(255,255,255,0.2); padding: 2px 6px; border-radius: 4px;">标准安全版</span></div>
            <div style="display: flex; gap: 8px;">
                <input type="file" id="excel-importer" accept=".csv" onchange="importFromExcel()" style="display: none;">
                <button onclick="document.getElementById('excel-importer').click()" class="mini-btn" style="background:#55826b; color:white; font-weight:bold; padding: 6px 12px;">📥 导入表格数据</button>
                <button onclick="exportToExcel()" class="mini-btn" style="background:#5ba37e; color:white; font-weight:bold; padding: 6px 12px;">📊 导出 Excel 表格</button>
            </div>
        </header>

        <div class="app-container">
            <div class="left-panel">
                <div class="tree-hollow">
                    <div style="font-size:11px; font-weight:bold; color:#846226; margin-bottom:4px; display:flex; justify-content:space-between;">
                        <span>🌲 森林树洞 · 截图/PDF/随手记</span>
                        <span id="scan-loading" style="color:var(--forest-leaf); display:none;">AI识别中...</span>
                    </div>
                    <input type="file" id="file-scanner" onchange="uploadAndScanFile()" style="font-size:11px; width:100%; margin-bottom:6px; color: var(--text-sub);">
                    <div id="hollow-pills" style="max-height:80px; overflow-y:auto; border-top:1px dashed #e1d6be; padding-top:4px;">
                        <span style="font-size:11px; color:#a49070; font-style:italic;">上传日剧截图或PDF，AI分词。</span>
                    </div>
                </div>

                <h3 id="panel-title">🌲 生词捕获终端</h3>
                <input type="hidden" id="in-id">

                <div class="form-group"><label>日语生词 *</label><input id="in-word" type="text" placeholder="例：遠慮する"></div>
                <div class="form-group"><label>当前情境台词 (选填)</label><textarea id="in-hint" rows="2" placeholder="贴入当前句子..."></textarea></div>
                <button id="btn-ai" onclick="runAIAssistant()" class="btn-action btn-ai">🪄 唤醒 AI 智能解析填表</button>

                <div style="font-size: 11px; font-weight: bold; color: var(--forest-leaf); margin-bottom: 6px;">📋 属性校对面板</div>
                <div class="form-group"><label>假名发音</label><input id="in-furi" type="text"></div>
                <div class="form-group"><label>中文释义</label><input id="in-zh" type="text"></div>
                <div class="form-group"><label>简易日解 (独立思维模式)</label><textarea id="in-ja" rows="2"></textarea></div>
                <div class="form-group"><label>情境出处</label><input id="in-source" type="text"></div>
                <div class="form-group"><label>标签分组</label><input id="in-tags" type="text" placeholder="日常 / 日剧"></div>
                <div class="form-group"><label>高频情境例句</label><textarea id="in-sentence" rows="2"></textarea></div>

                <div style="display:flex; gap:8px;">
                    <button id="btn-cancel-edit" onclick="cancelEditMode()" class="btn-action" style="background:#e9f0ed; display:none; flex:1;">取消</button>
                    <button id="btn-save" onclick="submitCard()" class="btn-action btn-submit" style="flex:2;">🌱 确认归档入库</button>
                </div>
            </div>

            <div class="right-panel">
                <div class="control-row">
                    <div id="tag-bar"></div>
                    <div class="view-switch">
                        <button id="sw-learning" onclick="switchStatusView('learning')" class="switch-btn active">📥 正在复习</button>
                        <button id="sw-mastered" onclick="switchStatusView('mastered')" class="switch-btn">🏆 已斩杀</button>
                    </div>
                </div>
                <div id="cards-container" class="cards-scroll-area"></div>
            </div>
        </div>

        <script>
            let currentTag = "全部"; let currentStatus = "learning";

            document.addEventListener('paste', async (e) => {
                const items = e.clipboardData.items;
                for (let i = 0; i < items.length; i++) {
                    if (items[i].type.indexOf("image") !== -1) {
                        const file = items[i].getAsFile();
                        const formData = new FormData(); formData.append("file", file, "clipboard.png");
                        triggerDirectScan(formData);
                    }
                }
            });

            async function uploadAndScanFile() {
                const fileInput = document.getElementById('file-scanner');
                if (fileInput.files.length === 0) return;
                const formData = new FormData(); formData.append("file", fileInput.files[0]);
                triggerDirectScan(formData);
            }

            async function triggerDirectScan(formData) {
                const loading = document.getElementById('scan-loading');
                const hollow = document.getElementById('hollow-pills');
                loading.style.display = 'inline';
                try {
                    const res = await fetch('/api/insight/file-scan', { method: 'POST', body: formData });
                    const data = await res.json();
                    if(data.words && data.words.length > 0) {
                        hollow.innerHTML = data.words.map(w => `<span class="word-pill" onclick="claimWord('${w}')">${w}</span>`).join('');
                    } else { hollow.innerHTML = `<span style="font-size:11px; color:#a49070;">未提取到显著生词。</span>`; }
                } catch (e) { alert('文件扫描网络异常'); } finally { loading.style.display = 'none'; }
            }

            function claimWord(word) {
                document.getElementById('in-word').value = word;
                document.getElementById('in-hint').value = "";
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }

            async function runAIAssistant() {
                const wordInput = document.getElementById('in-word');
                const hintInput = document.getElementById('in-hint');
                const btn = document.getElementById('btn-ai');
                let cleanWord = wordInput.value.replace(/\[.*?\]\(.*?\)/g, "").replace(/[\[\]\(\)]/g, "").trim();
                wordInput.value = cleanWord;

                if(!cleanWord) { alert('请输入生词！'); return; }
                btn.innerText = "🍃 检索中..."; btn.disabled = true;

                try {
                    const res = await fetch('/api/ai-generate', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ word: cleanWord, hint_sentence: hintInput.value.trim() })
                    });
                    const data = await res.json();
                    if (data.error_type) { alert(data.msg); return; }

                    document.getElementById('in-furi').value = data.furigana || '';
                    document.getElementById('in-zh').value = data.meaning_zh || '';
                    document.getElementById('in-ja').value = data.meaning_ja || '';
                    document.getElementById('in-source').value = data.context_source || '通用';
                    document.getElementById('in-sentence').value = data.example_sentence || '';

                    let tag = data.tags || '日常';
                    if(tag.includes("常") || tag.includes("活")) tag = "日常";
                    if(tag.includes("剧") || tag.includes("漫")) tag = "日剧";
                    document.getElementById('in-tags').value = tag;
                } catch(e) { alert('网络通信异常'); } finally { btn.innerText = "🪄 唤醒 AI 智能解析填表"; btn.disabled = false; }
            }

            async function loadCards() {
                const res = await fetch(`/api/cards?tag=${encodeURIComponent(currentTag)}&filter_status=${currentStatus}`);
                const cards = await res.json();
                renderTagBar(["全部", "日常", "日剧"]); renderCards(cards);
            }

            function renderTagBar(tags) {
                document.getElementById('tag-bar').innerHTML = tags.map(tag => `
                    <button onclick="switchTag('${tag}')" class="tag-btn ${currentTag === tag ? 'active' : ''}">${tag}</button>
                `).join('');
            }
            function switchTag(tag) { currentTag = tag; loadCards(); }
            function switchStatusView(status) {
                currentStatus = status;
                document.getElementById('sw-learning').classList.toggle('active', status === 'learning');
                document.getElementById('sw-mastered').classList.toggle('active', status === 'mastered');
                loadCards();
            }

            function renderCards(cards) {
                const container = document.getElementById('cards-container');
                if(!cards || cards.length === 0) { container.innerHTML = `<div style="text-align:center; padding:40px; color:var(--text-sub);">空空如也。</div>`; return; }

                container.innerHTML = cards.map(c => `
                    <div class="card-perspective">
                        <div class="card-rotator" onclick="toggleCardFlip(event, this)">
                            <div class="face-front" style="display:flex; flex-direction:column; justify-content:space-between;">
                                <div>
                                    <span style="font-size:10px; color:var(--forest-leaf); background:#e9f0ed; padding:1px 6px; border-radius:4px; font-weight:bold;">${c.context_source}</span>
                                </div>
                                <div style="margin: 4px 0; display:flex; align-items:baseline; gap:8px;">
                                    <div style="font-size: 19px; font-weight: bold; color: var(--forest-dark);">${c.word}</div>
                                    <div style="font-size: 12px; color: var(--forest-leaf);">[${c.furigana}]</div>
                                </div>
                                <div style="font-size:11px; color:var(--text-sub); border-top: 1px dotted #e2e9e6; padding-top:4px; line-height:1.4; word-break:break-all;">
                                    ${c.example_sentence}
                                </div>
                            </div>
                            <div class="face-back" style="display:flex; flex-direction:column; justify-content:space-between;">
                                <div>
                                    <span style="font-size:11px; font-weight:bold; color:var(--forest-leaf);">${c.word}</span>
                                </div>
                                ${c.meaning_ja ? `<div style="font-size:10px; color:var(--text-main); background:#f0f4f2; padding:3px 6px; border-radius:4px; line-height:1.3; margin: 2px 0;">${c.meaning_ja}</div>` : ''}
                                <div style="font-size:12px; color:var(--text-sub); font-weight:bold; border-top: 1px dashed #d3ded9; padding-top:4px; word-break:break-all;">
                                    中文：<span style="color:#335c4b; font-weight:normal;">${c.meaning_zh}</span>
                                </div>
                            </div>
                        </div>
                        <div class="card-actions">
                            <button onclick="enterEditMode(${JSON.stringify(c).replace(/"/g, '&quot;')})" class="mini-btn">✏️</button>
                            ${c.status === 'learning' ? 
                                `<button onclick="changeStatus(${c.id}, 'mastered')" class="mini-btn" style="color:var(--success)">🌱</button>` : 
                                `<button onclick="changeStatus(${c.id}, 'learning')" class="mini-btn">🍂</button>`
                            }
                            <button onclick="deleteCard(${c.id})" class="mini-btn del">🗑️</button>
                        </div>
                    </div>
                `).join('');
            }

            function toggleCardFlip(e, element) {
                if(e.target.tagName.toLowerCase() === 'button' || e.target.classList.contains('mini-btn')) return;
                element.classList.toggle('is-flipped');
            }

            function enterEditMode(card) {
                document.getElementById('panel-title').innerText = "✏️ 正在修改生词卡片";
                document.getElementById('in-id').value = card.id;
                document.getElementById('in-word').value = card.word;
                document.getElementById('in-furi').value = card.furigana;
                document.getElementById('in-zh').value = card.meaning_zh;
                document.getElementById('in-ja').value = card.meaning_ja || '';
                document.getElementById('in-source').value = card.context_source;
                document.getElementById('in-sentence').value = card.example_sentence;
                document.getElementById('in-tags').value = card.tags;

                document.getElementById('btn-cancel-edit').style.display = 'block';
                document.getElementById('btn-save').innerText = "💾 保存修改并更新";
                window.scrollTo({ top: 0, behavior: 'smooth' });
            }

            function cancelEditMode() {
                document.getElementById('panel-title').innerText = "🌲 生词捕获终端";
                document.getElementById('in-id').value = ""; document.getElementById('in-word').value = "";
                document.getElementById('in-hint').value = ""; document.getElementById('in-furi').value = "";
                document.getElementById('in-zh').value = ""; document.getElementById('in-ja').value = "";
                document.getElementById('in-source').value = ""; document.getElementById('in-sentence').value = ""; document.getElementById('in-tags').value = "";
                document.getElementById('btn-cancel-edit').style.display = 'none';
                document.getElementById('btn-save').innerText = "🌱 确认归档入库";
            }

            async function submitCard() {
                const idVal = document.getElementById('in-id').value;
                const card = {
                    word: document.getElementById('in-word').value.trim(), furigana: document.getElementById('in-furi').value.trim(),
                    meaning_zh: document.getElementById('in-zh').value.trim(), meaning_ja: document.getElementById('in-ja').value.trim(),
                    context_source: document.getElementById('in-source').value.trim() || '通用', example_sentence: document.getElementById('in-sentence').value.trim(),
                    tags: document.getElementById('in-tags').value.trim() || '日常'
                };
                if(idVal) card.id = parseInt(idVal);
                if(!card.word || !card.meaning_zh || !card.furigana) { alert('必填项不能为空！'); return; }
                const res = await fetch('/api/cards', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(card) });
                if(res.ok) { cancelEditMode(); loadCards(); }
            }

            async function deleteCard(id) {
                if(!confirm('确定要抹除这张卡片吗？')) return;
                const res = await fetch(`/api/cards/${id}`, { method: 'DELETE' });
                if(res.ok) loadCards();
            }

            async function changeStatus(id, newStatus) {
                const res = await fetch(`/api/cards/${id}/status`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ status: newStatus }) });
                if(res.ok) loadCards();
            }

            function exportToExcel() { window.location.href = '/api/cards/export'; }

            async function importFromExcel() {
                const fileInput = document.getElementById('excel-importer');
                if (fileInput.files.length === 0) return;
                
                const file = fileInput.files[0];
                if (!confirm(`确定要从文件 [${file.name}] 导入生词数据吗？`)) {
                    fileInput.value = "";
                    return;
                }
                
                const formData = new FormData();
                formData.append("file", file);
                
                try {
                    const res = await fetch('/api/cards/import', {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    if (res.ok) {
                        alert(`🎉 成功导入 ${data.imported_count} 条生词数据！`);
                        loadCards();
                    } else {
                        alert(`❌ 导入失败：${data.detail || '未知错误'}`);
                    }
                } catch (e) {
                    alert('❌ 网络通信异常，无法导入文件');
                } finally {
                    fileInput.value = "";
                }
            }

            window.onload = loadCards;
        </script>
    </body>
    </html>
    """


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=7860, reload=True)
