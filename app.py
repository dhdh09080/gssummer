import streamlit as st
import easyocr
from PIL import Image
import numpy as np
import pandas as pd
import re
import os
import hashlib
from streamlit_paste_button import paste_image_button as pbutton

# 페이지 기본 설정
st.set_page_config(page_title="현장 안전/보건 데이터 자동화", layout="wide")

DATA_FILE = "worker_data.csv"

# 세션 상태에 데이터프레임 초기화
if 'df' not in st.session_state:
    if os.path.exists(DATA_FILE):
        st.session_state.df = pd.read_csv(DATA_FILE)
    else:
        st.session_state.df = pd.DataFrame(columns=["시간", "업체", "공종", "현장명", "이름", "혈액형", "국적", "체온"])

# 중복 처리 방지를 위한 이미지 고유값(해시) 저장소
if 'processed_images' not in st.session_state:
    st.session_state.processed_images = set()

# 이미지에서 고유값을 추출하는 함수
def get_image_hash(image):
    return hashlib.md5(image.tobytes()).hexdigest()

@st.cache_resource
def load_reader():
    return easyocr.Reader(['ko', 'en'])

reader = load_reader()

st.title("👷 안전모 및 체온계 자동 인식 시스템")
st.markdown("사진을 업로드하거나, 화면을 캡처한 후 **클립보드에서 붙여넣기(Ctrl+V)** 하세요.")

# 업로드와 붙여넣기 창을 좌우로 배치
col1, col2 = st.columns(2)

with col1:
    uploaded_files = st.file_uploader("📂 파일 선택 (또는 여기를 클릭하고 Ctrl+V)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

with col2:
    st.write("📋 캡처한 사진을 아래 버튼을 눌러 붙여넣기")
    paste_result = pbutton("클립보드에서 이미지 붙여넣기")

# 이번에 분석할 이미지들을 모아둘 리스트
images_to_process = []

# 1. 파일 업로드 또는 Ctrl+V(업로드 창 안에서)로 들어온 이미지 처리
if uploaded_files:
    for f in uploaded_files:
        img = Image.open(f)
        img_hash = get_image_hash(img)
        # 아직 분석하지 않은 새로운 이미지일 경우에만 리스트에 추가
        if img_hash not in st.session_state.processed_images:
            images_to_process.append({"name": f.name, "image": img, "hash": img_hash})

# 2. 전용 클립보드 붙여넣기 버튼으로 들어온 이미지 처리
if paste_result.image_data is not None:
    img = paste_result.image_data
    img_hash = get_image_hash(img)
    if img_hash not in st.session_state.processed_images:
        images_to_process.append({"name": "클립보드_캡처_이미지.png", "image": img, "hash": img_hash})

# 등록된 이미지가 있다면 분석 시작
if images_to_process:
    for item in images_to_process:
        img = item["image"]
        img_name = item["name"]
        img_hash = item["hash"]
        
        st.image(img, caption=f'업로드 완료: {img_name}', width=300)
        
        with st.spinner(f"'{img_name}' 분석 중..."):
            image_np = np.array(img)
            results = reader.readtext(image_np)
            
            company, job_type, site_name, name, blood_type, nationality, temperature = "", "", "", "", "", "내국인", ""
            
            parsed_data = []
            for (bbox, text, prob) in results:
                text_clean = text.replace(" ", "").strip()
                cx = sum([p[0] for p in bbox]) / 4
                cy = sum([p[1] for p in bbox]) / 4
                parsed_data.append({"text": text_clean, "raw_text": text, "x": cx, "y": cy})
            
            for data_item in parsed_data:
                temp_match = re.search(r'(3[5-9]\.\d|4[0-2]\.\d)', data_item["text"])
                if temp_match:
                    temperature = temp_match.group()
            
            if parsed_data:
                avg_x = sum([d["x"] for d in parsed_data]) / len(parsed_data)
                avg_y = sum([d["y"] for d in parsed_data]) / len(parsed_data)
                
                job_keywords = ["형틀", "철근", "콘크리트", "비계", "전기", "설비", "안전"]
                country_keywords = ["CHINA", "중국", "VIETNAM", "베트남", "MYANMAR", "미얀마", "외국인"]
                
                for data_item in parsed_data:
                    txt = data_item["text"]
                    raw_txt = data_item["raw_text"]
                    x, y = data_item["x"], data_item["y"]
                    
                    if re.search(r'(A|B|O|AB)형', txt, re.IGNORECASE):
                        blood_type = re.search(r'(A|B|O|AB)형', txt, re.IGNORECASE).group()
                    
                    for c in country_keywords:
                        if c in txt.upper():
                            nationality = raw_txt
                    
                    for j in job_keywords:
                        if j in txt:
                            job_type = j
                            
                    if ("자이" in txt or "건설" in txt) and (x > avg_x):
                        site_name = raw_txt
                    elif "건설" in txt and (x < avg_x):
                        company = raw_txt
                        
                    if x > avg_x and y > avg_y and re.fullmatch(r'^[가-힣]{2,4}$', txt):
                        if not any(k in txt for k in job_keywords + ["자이", "건설"]):
                            name = txt

            # 분석 결과 데이터 구성
            new_data = pd.DataFrame([{
                "시간": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S"),
                "업체": company,
                "공종": job_type,
                "현장명": site_name,
                "이름": name,
                "혈액형": blood_type,
                "국적": nationality,
                "체온": temperature
            }])
            
            # 리스트에 추가 후 CSV 저장
            st.session_state.df = pd.concat([st.session_state.df, new_data], ignore_index=True)
            st.session_state.df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')
            
            # 처리가 끝난 이미지는 해시를 저장하여 다시 분석하지 않도록 잠금
            st.session_state.processed_images.add(img_hash)

st.divider()

st.subheader("📊 자동 저장된 데이터 리스트")
st.dataframe(st.session_state.df, use_container_width=True)

csv = st.session_state.df.to_csv(index=False, encoding='utf-8-sig')
st.download_button(
    label="📥 엑셀(CSV) 파일로 다운로드",
    data=csv,
    file_name="현장_측정데이터.csv",
    mime="text/csv",
)
