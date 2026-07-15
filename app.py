import streamlit as st
import json
import os
import csv
import io
import base64
from zhipuai import ZhipuAI
from pypdf import PdfReader

# ==========================================
# 1. 初始化页面配置与样式
# ==========================================
st.set_page_config(
    page_title="🍃 情境生词消灭器 - 豪华免费版",
    page_icon="🍃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入 CSS 样式，保留森林绿的清新风格
# 注入 CSS 样式，美化 Streamlit 默认的外观，保留森林绿的清新风格
st.markdown(
    """
    <style>
        .main { background-color: #f4f7f5; }
        .stButton>button { background-color: #4a7c6c; color: white; border-radius: 8px; border: none; }
        .stButton>button:hover { background-color: #2d4a43; color: white; }
        .word-title { font-size: 24px; font-weight: bold; color: #2d4a43; }
        .meaning-box { background-color: #e9f0ed; padding: 10px; border-radius: 8px; margin: 5px 0; border-left: 5px solid #4a7c6c; }
        .card-container { background: white; padding: 15px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 12px; border: 1px solid #e2e9e6; }
    </style>
    """, 
    unsafe-allow_index=True
)

# ==========================================
# 2. 智谱 AI 安全连接（精准绑定你的免费资源包）
# ==========================================
# 锁死你在 2026-10 到期前的 500万 GLM-4.7 文本体验包
FREE_TEXT_MODEL = "glm-4.7"

# 锁死你在 2026-08 到期前的 600万 GLM-4.6V 视觉体验包
FREE_VISION_MODEL = "glm-4.6v"

# 安全地从 Streamlit Secrets 中读取 API Key（本地运行时可在 .streamlit/secrets.toml 中配置）
if "ZHIPU_API_KEY" in st.secrets:
    api_key = st.secrets["ZHIPU_API_KEY"]
else:
    # 允许在界面上临时输入，方便本地调试
    api_key = st.sidebar.text_input("🔑 智谱 API Key", type="password", help="请在 Streamlit 部署面板或本地 Secrets 中配置 ZHIPU_API_KEY 以隐藏此框")

if api_key:
    client_ai = ZhipuAI(api_key=api_key)
else:
    st.warning("⚠️ 请在左侧边栏配置您的智谱 API Key，或者在 Secrets 中预设 ZHIPU_API_KEY！")
    client_ai = None

# ==========================================
# 3. 数据持久化（基于 Streamlit 缓存与本地文件）
# ==========================================
DB_FILE = "cards_db.json"
DEFAULT_CARDS = [
    {
        "id": 1, "word": "相棒", "furigana": "あいぼう",
        "meaning_ja": "一緒に仕事や行動をする大切なパートナーのこと。",
        "meaning_zh": "老搭档、死党、伙伴", "context_source": "日剧",
        "example_sentence": "お前は俺的最高の相棒だ。（你是我最好的搭档。）", "tags": "日剧", "status": "learning"
    },
    {
        "id": 2, "word": "一口", "furigana": "ひとくち",
        "meaning_ja": "食べ物や飲み物を、口の中に一度に入れる量。",
        "meaning_zh": "（吃/喝）一口", "context_source": "日常",
        "example_sentence": "これ、めちゃくちゃ美味しいから一口食べてみて！", "tags": "日常", "status": "learning"
    }
]

def load_db():
    if os.path.exists(DB_FILE) and os.path.getsize(DB_FILE) > 5:
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return DEFAULT_CARDS
    return DEFAULT_CARDS

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

if "cards" not in st.session_state:
    st.session_state.cards = load_db()

# ==========================================
# 4. 侧边栏功能区
# ==========================================
st.sidebar.title("🌲 森林树洞功能区")

# 4.1 导入与导出 CSV 数据
st.sidebar.subheader("📊 数据备份与恢复")

# 导出功能
csv_buffer = io.StringIO()
csv_buffer.write('\ufeff')  # 加上 UTF-8 BOM 避免 Excel 乱码
writer = csv.writer(csv_buffer)
writer.writerow(["生词", "假名发音", "日文释义", "中文含义", "情境出处", "高频生活例句", "标签", "掌握状态"])
for c in st.session_state.cards:
    status_zh = "已掌握" if c.get("status") == "mastered" else "正在复习"
    writer.writerow([c["word"], c["furigana"], c.get("meaning_ja", ""), c["meaning_zh"], c["context_source"], c["example_sentence"], c["tags"], status_zh])

st.sidebar.download_button(
    label="📥 导出 Excel (CSV)",
    data=csv_buffer.getvalue(),
    file_name="my_japanese_cards.csv",
    mime="text/csv",
)

# 导入功能
uploaded_csv = st.sidebar.file_uploader("📂 导入先前导出的 CSV 备份", type=["csv"])
if uploaded_csv:
    try:
        text_content = uploaded_csv.read().decode("utf-8-sig", errors="ignore")
        f_input = io.StringIO(text_content)
        reader = csv.reader(f_input)
        header = next(reader, None)
        if header and header[0] == "生词":
            new_id = max([c["id"] for c in st.session_state.cards]) + 1 if st.session_state.cards else 1
            imported_count = 0
            for row in reader:
                if not row or len(row) < 2:
                    continue
                word = row[0].strip()
                furigana = row[1].strip()
                if not word or not furigana:
                    continue
                
                st.session_state.cards.append({
                    "id": new_id, "word": word, "furigana": furigana,
                    "meaning_ja": row[2].strip() if len(row) > 2 else "",
                    "meaning_zh": row[3].strip() if len(row) > 3 else "",
                    "context_source": row[4].strip() if len(row) > 4 else "导入",
                    "example_sentence": row[5].strip() if len(row) > 5 else "",
                    "tags": row[6].strip() if len(row) > 6 else "日常",
                    "status": "mastered" if (len(row) > 7 and row[7].strip() == "已掌握") else "learning"
                })
                new_id += 1
                imported_count += 1
            save_db(st.session_state.cards)
            st.sidebar.success(f"🎉 成功导入 {imported_count} 条卡片数据！")
            st.rerun()
    except Exception as e:
        st.sidebar.error(f"解析失败: {str(e)}")

# 4.2 截图/PDF 分词扫描器（精准消耗 glm-4.6v）
st.sidebar.subheader("📸 智能扫描（图片/PDF）")
scanned_file = st.sidebar.file_uploader("上传日剧截图或PDF，AI分词", type=["pdf", "png", "jpg", "jpeg", "webp"])

extracted_words = []
if scanned_file and client_ai:
    with st.spinner("AI 正在解析原始文本并提取词汇..."):
        extracted_text = ""
        filename = scanned_file.name.lower()
        
        # 处理 PDF 文本
        if filename.endswith(".pdf"):
            try:
                reader = PdfReader(scanned_file)
                for page in reader.pages[:5]:
                    extracted_text += page.extract_text() or ""
            except Exception as e:
                st.sidebar.error(f"PDF解析失败: {str(e)}")
        # 处理图片 (精准绑定免费多模态大模型 glm-4.6v)
        else:
            try:
                image_bytes = scanned_file.read()
                base64_image = base64.b64encode(image_bytes).decode('utf-8')
                response = client_ai.chat.completions.create(
                    model=FREE_VISION_MODEL,
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
                st.sidebar.error(f"图片OCR失败: {str(e)}")
        
        # 利用大模型进行分词归纳 (文本处理交由免费的 glm-4.7)
        if extracted_text.strip():
            try:
                filter_prompt = (
                    "请从以下文本中提取出适合N4-N3级别的核心词汇。\n"
                    f"目标文本：\n{extracted_text}\n\n"
                    "请直接返回一个纯JSON格式的字符串数组，例：[\"単語1\", \"単語2\"]，不要使用 markdown 标记包裹。"
                )
                res = client_ai.chat.completions.create(
                    model=FREE_TEXT_MODEL,
                    messages=[{"role": "user", "content": filter_prompt}],
                    temperature=0.2
                )
                raw_arr = res.choices[0].message.content.strip()
                if raw_arr.startswith("```"):
                    raw_arr = raw_arr.split("\n", 1)[1].rsplit("\n", 1)[0]
                extracted_words = json.loads(raw_arr)
            except:
                extracted_words = [w.strip() for w in extracted_text.split() if w.strip()][:15]

if extracted_words:
    st.sidebar.write("📌 点击下方提取到的生词快速填表：")
    for w in extracted_words:
        if st.sidebar.button(f"👉 {w}", key=f"pill_{w}"):
            st.session_state["input_word"] = w
            st.rerun()

# ==========================================
# 5. 主页面：生词捕获终端与卡片库
# ==========================================
st.title("🍃 日语情境生词消灭器")

col_form, col_cards = st.columns([1.2, 2])

if "input_word" not in st.session_state:
    st.session_state["input_word"] = ""
if "ai_response" not in st.session_state:
    st.session_state["ai_response"] = {}

# 5.1 左侧：录入与AI自动解析面板 (精准消耗 glm-4.7)
with col_form:
    st.subheader("🌲 生词捕获终端")
    
    in_word = st.text_input("日语生词 *", value=st.session_state["input_word"])
    in_hint = st.text_area("当前情境台词 (选填)", placeholder="贴入当前句子...")
    
    # 智能解析
    if st.button("🪄 唤醒 AI 智能解析填表") and client_ai:
        if not in_word:
            st.error("请输入要解析的日语生词！")
        else:
            with st.spinner("高级 AI 模型正在分析中..."):
                prompt = (
                    "你是一个精通中日双语的日语教学专家。请为以下日语生词进行解析。\n"
                    f"待解析生词：{in_word}\n"
                    f"用户提供的情境提示：{in_hint if in_hint else '无'}\n\n"
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
                        model=FREE_TEXT_MODEL,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                    )
                    raw_text = response.choices[0].message.content.strip()
                    if raw_text.startswith("```"):
                        raw_text = raw_text.split("\n", 1)[1].rsplit("\n", 1)[0]
                    st.session_state["ai_response"] = json.loads(raw_text)
                except Exception as e:
                    st.error(f"大模型解析失败: {str(e)}")

    # 属性校对面板
    st.markdown("##### 📋 属性校对面板")
    ai_data = st.session_state["ai_response"]
    
    furi = st.text_input("假名发音", value=ai_data.get("furigana", ""))
    zh = st.text_input("中文释义", value=ai_data.get("meaning_zh", ""))
    ja = st.text_area("简易日解 (建立日本语思维)", value=ai_data.get("meaning_ja", ""))
    source = st.text_input("情境出处", value=ai_data.get("context_source", "通用"))
    tags = st.text_input("标签分组 (日常 / 日剧)", value=ai_data.get("tags", "日常"))
    sentence = st.text_area("高频情境例句", value=ai_data.get("example_sentence", ""))

    if st.button("🌱 确认归档入库"):
        if not in_word or not zh or not furi:
            st.error("生词、假名发音及中文释义为必填项！")
        else:
            new_id = max([c["id"] for c in st.session_state.cards]) + 1 if st.session_state.cards else 1
            new_card = {
                "id": new_id, "word": in_word, "furigana": furi, "meaning_ja": ja,
                "meaning_zh": zh, "context_source": source, "example_sentence": sentence,
                "tags": tags if tags in ["日常", "日剧"] else "日常", "status": "learning"
            }
            st.session_state.cards.append(new_card)
            save_db(st.session_state.cards)
            st.success("🎉 卡片归档成功！")
            st.session_state["input_word"] = ""
            st.session_state["ai_response"] = {}
            st.rerun()

# 5.2 右侧：生词卡片展示面板
with col_cards:
    st.subheader("🗂️ 我的生词卡片库")
    
    col_t, col_s = st.columns(2)
    with col_t:
        tag_filter = st.selectbox("标签筛选", ["全部", "日常", "日剧"])
    with col_s:
        status_filter = st.radio("学习状态", ["正在复习", "已斩杀"], horizontal=True)
    
    status_key = "learning" if status_filter == "正在复习" else "mastered"
    
    filtered_cards = st.session_state.cards
    if tag_filter != "全部":
        filtered_cards = [c for c in filtered_cards if c["tags"] == tag_filter]
    filtered_cards = [c for c in filtered_cards if c.get("status", "learning") == status_key]
    
    if not filtered_cards:
        st.info("当前筛选条件下无生词卡片，快去左侧捕获生词吧！")
    else:
        for card in reversed(filtered_cards):
            card_id = card["id"]
            
            with st.container():
                st.markdown(f"""
                <div class="card-container">
                    <span style="font-size:11px; background:#4a7c6c; color:white; padding:2px 6px; border-radius:4px;">{card['context_source']}</span>
                    <div class="word-title">{card['word']} <span style="font-size:14px; color:#60756c; font-weight:normal;">[{card['furigana']}]</span></div>
                    <div style="font-size:13px; color:#555; margin-top:5px;"><b>例句：</b>{card['example_sentence']}</div>
                </div>
                """, unsafe-allow_index=True)
                
                # 平替卡片反转交互
                with st.expander("🔍 翻面查看释义 & 释义详情"):
                    if card['meaning_ja']:
                        st.markdown(f"**💡 日解 (思维建立)：**")
                        st.markdown(f"<div class='meaning-box'>{card['meaning_ja']}</div>", unsafe-allow_index=True)
                    st.markdown(f"🇨🇳 中文释义：")
                
                # 操作行
                btn_col1, btn_col2, _ = st.columns([1, 1, 4])
                with btn_col1:
                    if card["status"] == "learning":
                        if st.button("🏆 斩杀", key=f"master_{card_id}"):
                            card["status"] = "mastered"
                            save_db(st.session_state.cards)
                            st.rerun()
                    else:
                        if st.button("🍂 召回", key=f"retrieve_{card_id}"):
                            card["status"] = "learning"
                            save_db(st.session_state.cards)
                            st.rerun()
                with btn_col2:
                    if st.button("🗑️ 抹除", key=f"del_{card_id}"):
                        st.session_state.cards = [c for c in st.session_state.cards if c["id"] != card_id]
                        save_db(st.session_state.cards)
                        st.rerun()
                
                st.markdown("<hr style='margin:10px 0; border:0; border-top:1px dashed #ccc;'/>", unsafe-allow_index=True)
