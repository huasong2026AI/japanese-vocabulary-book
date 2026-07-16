import streamlit as st
import json
import os
import io
import base64
import pandas as pd
from zhipuai import ZhipuAI
from pypdf import PdfReader

# ==========================================
# 1. 页面配置与精致森林绿样式（全局字体缩小）
# ==========================================
st.set_page_config(
    page_title="情境生词消灭器 🍃",
    page_icon="🍃",
    layout="wide",
    initial_sidebar_state="collapsed" # 手机端默认收起侧边栏，保持主页清爽
)

# 注入全局 CSS：缩小字体、精简排版、美化虚线框、统一按钮样式
st.markdown("""
    <style>
    /* 全局基础字体调小，视觉更精致 */
    html, body, [class*="css"], p, ul, li {
        font-size: 14px !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    h1 { font-size: 1.8rem !important; margin-bottom: 5px !important; }
    h2 { font-size: 1.4rem !important; margin-top: 10px !important; }
    h3 { font-size: 1.1rem !important; }
    
    :root {
        --primary-color: #4a7c6c;
    }
    
    /* 统一所有主要按钮（导出、表单提交等）的底色与样式 */
    .stButton>button, 
    .stDownloadButton>button {
        background-color: #4a7c6c !important;
        color: white !important;
        border-radius: 6px !important;
        font-size: 13px !important;
        padding: 4px 12px !important;
        border: 1px solid #4a7c6c !important;
        height: 38px !important;
        line-height: 24px !important;
        box-sizing: border-box !important;
        width: 100% !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    
    .stButton>button:hover, 
    .stDownloadButton>button:hover {
        background-color: #2d4a43 !important;
        border-color: #2d4a43 !important;
        color: white !important;
    }
    
    /* 移除表单的原生粗框 */
    form[data-testid="stForm"] {
        border: none !important;
        padding: 0px !important;
    }

    /* 原生 border 容器伪装成漂亮的森林虚线树洞 */
    div[data-testid="stVerticalBlockBorderContainer"] {
        border: 2px dashed #8ba89e !important;
        background-color: #fdfaf4 !important;
        border-radius: 10px !important;
        padding: 12px !important;
    }
    
    /* 极致美化树洞的 Upload 组件 */
    div[data-testid="stFileUploader"] {
        background-color: transparent !important;
        border: none !important;
        padding: 0px !important;
    }
    /* 隐藏上传组件自带的各种多余提示和拖拽区，只留一个干净的按钮 */
    div[data-testid="stFileUploader"] section {
        padding: 0px !important;
    }
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] {
        padding: 0px !important;
        border: none !important;
        background: transparent !important;
    }
    div[data-testid="stFileUploader"] [data-testid="stFileUploaderDropzone"] > div {
        display: none !important; /* 隐藏拖拽文字提示 */
    }

    /* 树洞里的 Upload 按钮美化得小巧一点 */
    .hollow-container div[data-testid="stFileUploader"] button {
        background-color: #8ba89e !important;
        color: white !important;
        border: none !important;
        border-radius: 4px !important;
        padding: 2px 10px !important;
        font-size: 12px !important;
        height: 30px !important;
    }
    .hollow-container div[data-testid="stFileUploader"] button:hover {
        background-color: #4a7c6c !important;
    }

    /* 生词胶囊横向排列 */
    div[data-testid="stHorizontalBlock"] .word-pill-container,
    .pill-wrapper {
        display: flex;
        flex-wrap: wrap;
        gap: 6px;
        margin-top: 5px;
        margin-bottom: 5px;
    }
    /* 自定义胶囊按钮样式 */
    div.stButton > button[kind="secondary"] {
        background-color: #ebdcb9 !important;
        color: #5a4525 !important;
        border: 1px solid #ebdcb9 !important;
        padding: 2px 10px !important;
        border-radius: 15px !important;
        font-size: 12px !important;
        font-weight: bold !important;
        height: auto !important;
        line-height: 1.2 !important;
        transition: all 0.2s ease;
    }
    div.stButton > button[kind="secondary"]:hover {
        background-color: #4a7c6c !important;
        color: white !important;
        border-color: #4a7c6c !important;
    }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 2. 安全读取 Streamlit Secrets (不泄露 Key)
# ==========================================
try:
    ZHIPU_API_KEY = st.secrets["ZHIPU_API_KEY"]
    client_ai = ZhipuAI(api_key=ZHIPU_API_KEY)
except Exception as e:
    st.error("⚠️ 未检测到 ZHIPU_API_KEY！请确保在 Streamlit Advanced Settings -> Secrets 中正确配置了该秘钥。")
    st.stop()

# ==========================================
# 3. 数据持久化逻辑（JSON）
# ==========================================
DB_FILE = "cards_db.json"

DEFAULT_CARDS = [
    {
        "id": 1, "word": "相棒", "furigana": "あいぼう",
        "meaning_ja": "一緒に仕事や行動をする大切なパートナーのこと。",
        "meaning_zh": "老搭档、死党、伙伴",
        "tags": "日剧", 
        "example_sentence": "1. お前は俺の最高の相棒だ。（你是我最好的搭档。）\n2. 相棒と一緒に新しいプロジェクトを始める。（和老搭档一起开始新项目。）\n3. 彼は私の仕事上の相棒です。（他是我的工作伙伴。）", 
        "status": "learning"
    },
    {
        "id": 2, "word": "一口", "furigana": "ひとくち",
        "meaning_ja": "食べ物や飲み物を、口の中に一度に入れる量。",
        "meaning_zh": "（吃/喝）一口",
        "tags": "日常", 
        "example_sentence": "1. これ、めちゃくちゃ美味しいから一口食べてみて！（这个超好吃，你吃一口试试！）\n2. ビールを一口飲む。（喝了一口啤酒。）\n3. 一口サイズのおにぎりを作る。（制作一口大小的饭团。）", 
        "status": "learning"
    }
]

def load_db():
    if os.path.exists(DB_FILE) and os.path.getsize(DB_FILE) > 5:
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_CARDS

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"本地保存数据库失败: {e}")

# 初始化所有的非组件绑定状态
if "cards" not in st.session_state:
    st.session_state.cards = load_db()
if "hollow_words" not in st.session_state:
    st.session_state.hollow_words = []
# 用于重置树洞 Upload 状态的计数器 key
if "uploader_counter" not in st.session_state:
    st.session_state.uploader_counter = 0

# 安全的临时字段中转
if "temp_word" not in st.session_state:
    st.session_state.temp_word = ""
if "temp_furi" not in st.session_state:
    st.session_state.temp_furi = ""
if "temp_zh" not in st.session_state:
    st.session_state.temp_zh = ""
if "temp_ja" not in st.session_state:
    st.session_state.temp_ja = ""
if "temp_tags" not in st.session_state:
    st.session_state.temp_tags = "日常"
if "temp_sentence" not in st.session_state:
    st.session_state.temp_sentence = ""

# ==========================================
# 4. 侧边栏（Sidebar）：统一备份与恢复系统
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ 备份与恢复系统")
    st.markdown("---")
    
    # 导出 CSV
    if st.session_state.cards:
        df = pd.DataFrame(st.session_state.cards)
        df_export = df.copy()
        df_export["status"] = df_export["status"].apply(lambda x: "已掌握" if x == "mastered" else "正在复习")
        csv_data = df_export.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📤 导出 CSV 备份",
            data=csv_data,
            file_name="my_japanese_cards.csv",
            mime="text/csv",
            use_container_width=True
        )
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # 导入 CSV（原生的完整组件，不强制隐藏内部结构，安全可靠，无任何多余箭头，点击即可导入）
    header_upload = st.file_uploader(
        "📥 导入 CSV 备份", 
        type=["csv"], 
        key="header_csv_uploader"
    )
    if header_upload is not None:
        try:
            df_import = pd.read_csv(header_upload, encoding="utf-8-sig")
            imported_cards = []
            new_id = max([c["id"] for c in st.session_state.cards]) + 1 if st.session_state.cards else 1
            for _, row in df_import.iterrows():
                status_raw = row.get("status", "正在复习")
                status = "mastered" if status_raw == "已掌握" else "learning"
                
                old_source = str(row.get("context_source", "")).strip()
                new_tags = str(row.get("tags", "日常")).strip()
                if old_source and old_source != "nan" and old_source != "通用":
                    new_tags = old_source

                imported_cards.append({
                    "id": new_id,
                    "word": str(row.get("word", "")).strip(),
                    "furigana": str(row.get("furigana", "")).strip(),
                    "meaning_ja": str(row.get("meaning_ja", "")).strip(),
                    "meaning_zh": str(row.get("meaning_zh", "")).strip(),
                    "example_sentence": str(row.get("example_sentence", "")).strip(),
                    "tags": new_tags,
                    "status": status
                })
                new_id += 1
            st.session_state.cards.extend(imported_cards)
            save_db(st.session_state.cards)
            st.sidebar.success(f"🎉 成功导入 {len(imported_cards)} 条数据！")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"导入解析失败：{e}")

# ==========================================
# 5. 主页面头部：彻底净化
# ==========================================
st.markdown("<h1 style='margin: 0; padding-bottom: 5px;'>🍃 情境生词消灭器</h1>", unsafe_allow_html=True)
st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)

# ==========================================
# 6. 主体布局：双栏极简
# ==========================================
left_col, right_col = st.columns([1, 1])

# --- 左栏：输入与 AI 生成端 ---
with left_col:
    
    # 🌲 森林树洞部分（全新升级：每次使用后更换 key，彻底解决第二次上传失效的问题）
    with st.container(border=True):
        st.markdown("<span style='color:#846226; font-weight:bold; font-size:13px;'>🌲 森林树洞 · 截图/PDF/随手记</span>", unsafe_allow_html=True)
        st.markdown("<span style='color:#a49070; font-size:11px; display:block; margin-bottom:6px;'>上传截图、PDF 或图片，AI 自动提取生词。</span>", unsafe_allow_html=True)
        
        st.markdown("<div class='hollow-container'>", unsafe_allow_html=True)
        
        # 使用自增 counter 来作为组件 key，只要发生了解析，key一变，第二次就能无缝上传
        uploader_key = f"hollow_uploader_{st.session_state.uploader_counter}"
        hollow_file = st.file_uploader(
            "选择文件", 
            type=["png", "jpg", "jpeg", "webp", "pdf"], 
            key=uploader_key, 
            label_visibility="collapsed"
        )
        
        if hollow_file is not None:
            file_bytes = hollow_file.read()
            filename = hollow_file.name.lower()
            extracted_text = ""
            
            if not st.session_state.hollow_words:
                with st.spinner("🌲 树洞正在努力解析文件..."):
                    try:
                        if filename.endswith(".pdf"):
                            reader = PdfReader(io.BytesIO(file_bytes))
                            for page in reader.pages[:5]:
                                extracted_text += page.extract_text() or ""
                        else:
                            # 多模态解析图片
                            base64_image = base64.b64encode(file_bytes).decode('utf-8')
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

                        if extracted_text.strip():
                            # 分词
                            filter_prompt = (
                                "请从以下文本中提取出适合N4-N3级别的核心词汇。\n"
                                f"目标文本：\n{extracted_text}\n\n"
                                "请直接返回一个纯JSON格式的字符串数组，例：[\"単語1\", \"単語2\"]，不要输出任何非 JSON 字符。"
                            )
                            res = client_ai.chat.completions.create(
                                model="glm-4-flash",
                                messages=[{"role": "user", "content": filter_prompt}],
                                temperature=0.2
                            )
                            raw_arr = res.choices[0].message.content.strip()
                            if raw_arr.startswith("```"):
                                raw_arr = raw_arr.split("\n", 1)[1].rsplit("\n", 1)[0]
                            st.session_state.hollow_words = json.loads(raw_arr)
                            
                            # 解析完后，自增计数器，下一次用户点击上传时，使用一个崭新的 uploader
                            st.session_state.uploader_counter += 1
                            st.rerun()
                    except Exception as e:
                        st.error(f"树洞解析出错: {e}")
                        st.session_state.hollow_words = ["解析失败"]
                        st.session_state.uploader_counter += 1

        st.markdown("</div>", unsafe_allow_html=True)

        # 渲染横向排列的单词胶囊
        if st.session_state.hollow_words:
            st.markdown("<span style='font-size:11px; font-weight:bold; color:var(--primary-color);'>💡 点击下方胶囊直接填入捕获终端：</span>", unsafe_allow_html=True)
            
            # 使用 5 列横向平铺胶囊
            cols = st.columns(5)
            for idx, w in enumerate(st.session_state.hollow_words):
                col_idx = idx % 5
                with cols[col_idx]:
                    if st.button(w, key=f"pill_{w}_{idx}", use_container_width=True):
                        st.session_state.temp_word = w
                        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # 🌲 生词捕获终端
    st.subheader("🌲 生词捕获终端")

    input_word = st.text_input("日语生词 *", value=st.session_state.temp_word)

    # ==========================================
    # 【唤醒 AI 智能解析】
    # ==========================================
    if st.button("🪄 唤醒 AI 智能解析填表"):
        if not input_word.strip():
            st.warning("请先输入生词")
        else:
            with st.spinner("🍃 智能助手正在深度解析中..."):
                try:
                    prompt = (
                        "你是一个精通中日双语的日语教学专家。请为以下日语生词进行解析。\n"
                        f"待解析生词：{input_word.strip()}\n\n"
                        "请严格按照以下 JSON 格式返回数据，不要包含任何 markdown 标记，不要有任何废话：\n"
                        "{\n"
                        '  "furigana": "该生词的纯假名发音",\n'
                        '  "meaning_zh": "该生词最准确的中文含义",\n'
                        '  "meaning_ja": "【绝对只能使用纯日语！】用简单易懂、符合N4水平的日语来解释该词的意思。",\n'
                        '  "tags": "只能从以下两个标签中选择一个填入：若属于动漫/日剧/台词填\'日剧\'，若是通用生活口语则填\'日常\'，或者你可以提炼出简洁的1-3字具体情境标签",\n'
                        '  "example_sentence": "【请务必给出三句不同使用语境、生活高频的完美日语例句，并分别附带对应的括号中文翻译。格式参考以下范例，必须换行排版：\\n1. 第一句例句（第一句的翻译）\\n2. 第二句例句（第二句的翻译）\\n3. 第三句例句（第三句的翻译）"\n'
                        "}"
                    )
                    response = client_ai.chat.completions.create(
                        model="glm-4-flash",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                    )
                    raw_text = response.choices[0].message.content.strip()
                    if raw_text.startswith("```"):
                        raw_text = raw_text.split("\n", 1)[1].rsplit("\n", 1)[0]
                    ai_data = json.loads(raw_text)

                    # 数据安全的放入临时中转变量中
                    st.session_state.temp_word = input_word.strip()
                    st.session_state.temp_furi = ai_data.get("furigana", "")
                    st.session_state.temp_zh = ai_data.get("meaning_zh", "")
                    st.session_state.temp_ja = ai_data.get("meaning_ja", "")
                    st.session_state.temp_tags = ai_data.get("tags", "日常")
                    st.session_state.temp_sentence = ai_data.get("example_sentence", "")

                    st.success("✨ 解析成功！数据已同步至下方的属性面板，请核对。")
                    st.rerun()
                except Exception as e:
                    st.error(f"智能解析失败: {e}")

    st.markdown("---")
    st.markdown("📋 **属性校对面板**")
    
    with st.form("clean_and_safe_form", clear_on_submit=False):
        
        col_f, col_z = st.columns(2)
        with col_f:
            furi_val = st.text_input("假名发音", value=st.session_state.temp_furi)
        with col_z:
            zh_val = st.text_input("中文释义", value=st.session_state.temp_zh)

        ja_val = st.text_area("简易日解 (独立思维模式)", value=st.session_state.temp_ja)
        tags_val = st.text_input("情境标签", value=st.session_state.temp_tags)
        sentence_val = st.text_area("高频情境例句 (已生成三句例句)", value=st.session_state.temp_sentence)

        submit_btn = st.form_submit_button("🌱 确认归档入库", use_container_width=True)
        
        if submit_btn:
            if not input_word.strip() or not zh_val.strip() or not furi_val.strip():
                st.error("生词、假名与中文释义不能为空！")
            else:
                new_card = {
                    "id": max([c["id"] for c in st.session_state.cards]) + 1 if st.session_state.cards else 1,
                    "word": input_word.strip(),
                    "furigana": furi_val.strip(),
                    "meaning_ja": ja_val.strip(),
                    "meaning_zh": zh_val.strip(),
                    "example_sentence": sentence_val.strip(),
                    "tags": tags_val.strip() if tags_val.strip() else "日常",
                    "status": "learning"
                }
                st.session_state.cards.append(new_card)
                save_db(st.session_state.cards)
                
                # 安全地清空中转值
                st.session_state.temp_word = ""
                st.session_state.temp_furi = ""
                st.session_state.temp_zh = ""
                st.session_state.temp_ja = ""
                st.session_state.temp_tags = "日常"
                st.session_state.temp_sentence = ""
                st.session_state.hollow_words = []
                
                st.success(f"生词「{input_word}」已成功归档！")
                st.rerun()

# --- 右栏：原生折叠卡片列表与过滤 ---
with right_col:
    st.subheader("📚 词库检索与复习")

    # 顶层过滤器
    col_filter_t, col_filter_s = st.columns(2)
    with col_filter_t:
        tag_options = ["全部", "日常", "日剧"]
        for c in st.session_state.cards:
            t = c.get("tags", "日常")
            if t not in tag_options:
                tag_options.append(t)
        selected_tag = st.selectbox("标签筛选", tag_options)
    with col_filter_s:
        selected_status = st.radio("学习状态", ["正在复习", "已掌握"], horizontal=True)

    status_key = "learning" if selected_status == "正在复习" else "mastered"

    # 数据过滤
    filtered_cards = st.session_state.cards
    if selected_tag != "全部":
        filtered_cards = [c for c in filtered_cards if selected_tag in c.get("tags", "")]
    filtered_cards = [c for c in filtered_cards if c.get("status", "learning") == status_key]

    # 按倒序展示
    filtered_cards = filtered_cards[::-1]

    if not filtered_cards:
        st.info("当前筛选下没有卡片，快去左侧捕获新词吧！")
    else:
        for idx, card in enumerate(filtered_cards):
            card_id = card["id"]
            card_label = f"🏷️ {card.get('tags', '日常')} | {card['word']} 【{card['furigana']}】"
            
            with st.expander(card_label, expanded=False):
                st.markdown(f"**中文含义**：<span style='color:#c96868; font-weight:bold;'>{card['meaning_zh']}</span>", unsafe_allow_html=True)
                if card.get("meaning_ja"):
                    st.markdown(f"**日文释义** (N4纯日解)：\n> {card['meaning_ja']}")
                if card.get("example_sentence"):
                    st.markdown(f"**例句情境**：\n\n{card['example_sentence']}")
                
                # 操作按键
                col_btn1, col_btn2, col_btn3 = st.columns([2, 2, 1])
                with col_btn1:
                    if card["status"] == "learning":
                        if st.button("🌱 斩杀 (掌握)", key=f"mast_{card_id}_{idx}"):
                            for c in st.session_state.cards:
                                if c["id"] == card_id:
                                    c["status"] = "mastered"
                            save_db(st.session_state.cards)
                            st.rerun()
                    else:
                        if st.button("🍂 召回 (复习)", key=f"relearn_{card_id}_{idx}"):
                            for c in st.session_state.cards:
                                if c["id"] == card_id:
                                    c["status"] = "learning"
                            save_db(st.session_state.cards)
                            st.rerun()
                with col_btn2:
                    if st.button("✏️ 载入编辑", key=f"edit_{card_id}_{idx}"):
                        st.session_state.temp_word = card["word"]
                        st.session_state.temp_furi = card["furigana"]
                        st.session_state.temp_zh = card["meaning_zh"]
                        st.session_state.temp_ja = card["meaning_ja"]
                        st.session_state.temp_tags = card.get("tags", "日常")
                        st.session_state.temp_sentence = card["example_sentence"]
                        st.rerun()
                with col_btn3:
                    if st.button("🗑️", key=f"del_{card_id}_{idx}"):
                        st.session_state.cards = [c for c in st.session_state.cards if c["id"] != card_id]
                        save_db(st.session_state.cards)
                        st.success("卡片已删除")
                        st.rerun()
