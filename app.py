import streamlit as st
import json
import os
import io
import base64
import pandas as pd
from zhipuai import ZhipuAI
from pypdf import PdfReader

# ==========================================
# 1. 页面基本配置与森林绿风格微调
# ==========================================
st.set_page_config(
    page_title="情境生词消灭器 🍃",
    page_icon="🍃",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 注入森林绿主题样式（增加了森林树洞虚线框和胶囊按钮的样式）
st.markdown("""
    <style>
    :root {
        --primary-color: #4a7c6c;
    }
    .stButton>button {
        background-color: #4a7c6c !important;
        color: white !important;
        border-radius: 8px !important;
    }
    .stButton>button:hover {
        background-color: #2d4a43 !important;
        color: white !important;
    }
    /* 森林树洞虚线卡片 */
    .tree-hollow-box {
        background-color: #fdfaf4;
        border: 2px dashed #8ba89e;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 20px;
    }
    /* 生词胶囊样式 */
    div.stButton > button.word-pill-btn {
        background-color: #ebdcb9 !important;
        color: #5a4525 !important;
        border: none !important;
        padding: 4px 10px !important;
        border-radius: 14px !important;
        font-size: 12px !important;
        margin: 4px !important;
        font-weight: bold !important;
        display: inline-block !important;
        width: auto !important;
    }
    div.stButton > button.word-pill-btn:hover {
        background-color: #4a7c6c !important;
        color: white !important;
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
        "meaning_zh": "老搭档、死党、伙伴", "context_source": "日剧",
        "example_sentence": "お前は俺の最高の相棒だ。（你是我最好的搭档。）", "tags": "日剧", "status": "learning"
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
            pass
    return DEFAULT_CARDS

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        st.error(f"本地保存数据库失败: {e}")

# 初始化 Session State
if "cards" not in st.session_state:
    st.session_state.cards = load_db()
if "input_fields" not in st.session_state:
    st.session_state.input_fields = {}
if "hollow_words" not in st.session_state:
    st.session_state.hollow_words = []
if "claimed_word" not in st.session_state:
    st.session_state.claimed_word = ""

# ==========================================
# 4. Streamlit 页面头部与导入导出
# ==========================================
st.title("🍃 情境生词消灭器 (Streamlit 安全云部署版)")

col_header_left, col_header_right = st.columns([2, 1])

with col_header_right:
    # 导出 CSV 备份
    if st.session_state.cards:
        df = pd.DataFrame(st.session_state.cards)
        df_export = df.copy()
        df_export["status"] = df_export["status"].apply(lambda x: "已掌握" if x == "mastered" else "正在复习")
        csv_data = df_export.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            label="📊 导出 CSV 表格备份",
            data=csv_data,
            file_name="my_japanese_cards.csv",
            mime="text/csv",
        )

    # 导入 CSV 备份
    uploaded_file = st.file_uploader("📥 导入 CSV 表格", type=["csv"], label_visibility="collapsed")
    if uploaded_file is not None:
        try:
            df_import = pd.read_csv(uploaded_file, encoding="utf-8-sig")
            imported_cards = []
            new_id = max([c["id"] for c in st.session_state.cards]) + 1 if st.session_state.cards else 1
            for _, row in df_import.iterrows():
                status_raw = row.get("status", "正在复习")
                status = "mastered" if status_raw == "已掌握" else "learning"
                imported_cards.append({
                    "id": new_id,
                    "word": str(row.get("word", "")).strip(),
                    "furigana": str(row.get("furigana", "")).strip(),
                    "meaning_ja": str(row.get("meaning_ja", "")).strip(),
                    "meaning_zh": str(row.get("meaning_zh", "")).strip(),
                    "context_source": str(row.get("context_source", "导入")).strip(),
                    "example_sentence": str(row.get("example_sentence", "")).strip(),
                    "tags": str(row.get("tags", "日常")).strip(),
                    "status": status
                })
                new_id += 1
            st.session_state.cards.extend(imported_cards)
            save_db(st.session_state.cards)
            st.success(f"🎉 成功导入 {len(imported_cards)} 条生词！")
        except Exception as e:
            st.error(f"导入解析失败，请检查格式：{e}")

# ==========================================
# 5. 主体布局：双栏极简
# ==========================================
left_col, right_col = st.columns([1, 1])

# --- 左栏：输入与 AI 生成端 ---
with left_col:
    # 🌲 森林树洞部分（完美移植虚线框效果）
    st.markdown('<div class="tree-hollow-box">', unsafe_allow_html=True)
    st.markdown("<span style='color:#846226; font-weight:bold; font-size:14px;'>🌲 森林树洞 · 截图/PDF/随手记</span>", unsafe_allow_html=True)
    st.markdown("<span style='color:#a49070; font-size:12px; display:block; margin-bottom:8px;'>上传日剧截图、PDF 或图片，AI 自动提取生词。</span>", unsafe_allow_html=True)
    
    hollow_file = st.file_uploader("选择文件", type=["png", "jpg", "jpeg", "webp", "pdf"], key="hollow_uploader", label_visibility="collapsed")
    
    if hollow_file is not None:
        file_bytes = hollow_file.read()
        filename = hollow_file.name.lower()
        extracted_text = ""
        
        # 避免每次重渲染都重新请求 AI，仅在数据为空时解析
        if not st.session_state.hollow_words:
            with st.spinner("🌲 树洞正在努力解析文件..."):
                try:
                    if filename.endswith(".pdf"):
                        reader = PdfReader(io.BytesIO(file_bytes))
                        for page in reader.pages[:5]:
                            extracted_text += page.extract_text() or ""
                    else:
                        # 使用多模态大模型 glm-4v-flash 解析图片
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
                        # 使用大模型提取出核心 N4/N3 词汇
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
                        st.session_state.hollow_words = json.loads(raw_arr)
                except Exception as e:
                    st.error(f"树洞解析出错: {e}")
                    st.session_state.hollow_words = ["解析失败"]

    # 渲染生词胶囊
    if st.session_state.hollow_words:
        st.markdown("<span style='font-size:12px; font-weight:bold; color:var(--primary-color);'>点击下方胶囊可直接填入终端：</span>", unsafe_allow_html=True)
        cols_pills = st.container()
        with cols_pills:
            # 渲染小胶囊
            for w in st.session_state.hollow_words:
                if st.button(w, key=f"pill_{w}", help="点击填入下方生词框"):
                    st.session_state.claimed_word = w
                    st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

    # 捕获终端
    st.subheader("🌲 生词捕获终端")

    # 如果有被点击选中的胶囊词，优先填入
    init_word = st.session_state.claimed_word if st.session_state.claimed_word else ""
    input_word = st.text_input("日语生词 *", value=init_word, key="in_word_actual")
    
    # 手动输入台词
    input_hint = st.text_area("当前情境台词 (选填)", placeholder="贴入当前句子...", key="in_hint")

    if st.button("🪄 唤醒 AI 智能解析填表"):
        if not input_word.strip():
            st.warning("请先输入生词")
        else:
            with st.spinner("🍃 智谱大模型 GLM-4-Flash 正在深度解析中..."):
                try:
                    prompt = (
                        "你是一个精通中日双语的日语教学专家。请为以下日语生词进行解析。\n"
                        f"待解析生词：{input_word.strip()}\n"
                        f"用户提供的情境提示：{input_hint.strip() if input_hint.strip() else '无'}\n\n"
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
                    response = client_ai.chat.completions.create(
                        model="glm-4-flash",
                        messages=[{"role": "user", "content": prompt}],
                        temperature=0.3,
                    )
                    raw_text = response.choices[0].message.content.strip()
                    if raw_text.startswith("```"):
                        raw_text = raw_text.split("\n", 1)[1].rsplit("\n", 1)[0]
                    ai_data = json.loads(raw_text)

                    st.session_state.input_fields = ai_data
                    st.success("✨ 解析成功！数据已同步至下方的属性面板，请核对。")
                except Exception as e:
                    st.error(f"大模型通讯或解析失败: {e}")

    # 属性校对面板
    st.markdown("---")
    st.markdown("📋 **属性校对面板**")

    cached = st.session_state.input_fields
    
    col_f, col_z = st.columns(2)
    with col_f:
        furi_val = st.text_input("假名发音", value=cached.get("furigana", ""), key="val_furi")
    with col_z:
        zh_val = st.text_input("中文释义", value=cached.get("meaning_zh", ""), key="val_zh")

    ja_val = st.text_area("简易日解 (独立思维模式)", value=cached.get("meaning_ja", ""), key="val_ja")
    
    col_s, col_t = st.columns(2)
    with col_s:
        source_val = st.text_input("情境出处", value=cached.get("context_source", "通用"), key="val_source")
    with col_t:
        tags_val = st.text_input("标签分组", value=cached.get("tags", "日常"), key="val_tags")

    sentence_val = st.text_area("高频情境例句", value=cached.get("example_sentence", ""), key="val_sentence")

    if st.button("🌱 确认归档入库", use_container_width=True):
        if not input_word.strip() or not zh_val.strip() or not furi_val.strip():
            st.error("生词、假名与中文释义不能为空！")
        else:
            new_card = {
                "id": max([c["id"] for c in st.session_state.cards]) + 1 if st.session_state.cards else 1,
                "word": input_word.strip(),
                "furigana": furi_val.strip(),
                "meaning_ja": ja_val.strip(),
                "meaning_zh": zh_val.strip(),
                "context_source": source_val.strip(),
                "example_sentence": sentence_val.strip(),
                "tags": tags_val.strip() if tags_val.strip() else "日常",
                "status": "learning"
            }
            st.session_state.cards.append(new_card)
            save_db(st.session_state.cards)
            # 归档后清空各种缓存状态
            st.session_state.input_fields = {}
            st.session_state.claimed_word = ""
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
            
            card_label = f"🏷️ {card['context_source']} | {card['word']} 【{card['furigana']}】"
            
            with st.expander(card_label, expanded=False):
                st.markdown(f"**中文含义**：<span style='color:#c96868; font-weight:bold;'>{card['meaning_zh']}</span>", unsafe_allow_html=True)
                if card.get("meaning_ja"):
                    st.markdown(f"**日文释义** (N4纯日解)：\n> {card['meaning_ja']}")
                if card.get("example_sentence"):
                    st.markdown(f"**例句情境**：\n* {card['example_sentence']}")
                
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
                        st.session_state.claimed_word = card["word"]
                        st.session_state.input_fields = {
                            "furigana": card["furigana"],
                            "meaning_zh": card["meaning_zh"],
                            "meaning_ja": card["meaning_ja"],
                            "context_source": card["context_source"],
                            "example_sentence": card["example_sentence"],
                            "tags": card["tags"]
                        }
                        st.success("已载入左侧！请直接在左侧修改后，重新点击“确认归档入库”。")
                        st.rerun()
                with col_btn3:
                    if st.button("🗑️", key=f"del_{card_id}_{idx}"):
                        st.session_state.cards = [c for c in st.session_state.cards if c["id"] != card_id]
                        save_db(st.session_state.cards)
                        st.success("卡片已删除")
                        st.rerun()
