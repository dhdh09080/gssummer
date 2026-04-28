import streamlit as st
import easyocr
from PIL import Image
import numpy as np
import pandas as pd
import re
import os

# 페이지 기본 설정
st.set_page_config(page_title="현장 안전/보건 데이터 자동화", layout="wide")

# 데이터 자동 저장을 위한 CSV 파일 경로
DATA_FILE = "worker_data.csv"

# 세션 상태(Session State)에 데이터프레임 초기화 (리스트 업 용도)
if 'df' not in st.session_state:
    if os.path.exists(DATA_FILE):
        st.session_state.df = pd.read_csv(DATA_FILE)
    else:
        st.session_state.df = pd.DataFrame(columns=["시간", "업체", "공종", "현장명", "이름", "혈액형", "국적", "체온"])

@st.cache_resource
def load_reader():
    # 한글, 영어 숫자 인식
    return easyocr.Reader(['ko', 'en'])

reader = load_reader()

st.title("👷 안전모 및 체온계 자동 인식 시스템")
st.markdown("사진을 업로드하면 자동으로 데이터를 추출하고 하단 리스트에 누적 저장합니다.")

# 파일 여러 개 동시 업로드 가능하도록 설정
uploaded_files = st.file_uploader("사진 업로드 (안전모 또는 체온계)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)

if uploaded_files:
    for uploaded_file in uploaded_files:
        image = Image.open(uploaded_file)
        st.image(image, caption=f'업로드: {uploaded_file.name}', width=300)
        
        with st.spinner(f"'{uploaded_file.name}' 분석 중..."):
            image_np = np.array(image)
            results = reader.readtext(image_np)
            
            # 초기값 세팅
            company, job_type, site_name, name, blood_type, nationality, temperature = "", "", "", "", "", "내국인", ""
            
            # EasyOCR은 텍스트의 바운딩 박스(좌표)를 함께 반환합니다.
            # 이를 통해 글자의 위치(좌/우, 상/하)를 대략적으로 유추할 수 있습니다.
            parsed_data = []
            for (bbox, text, prob) in results:
                text_clean = text.replace(" ", "").strip()
                # 중심 좌표 계산 (x, y)
                cx = sum([p[0] for p in bbox]) / 4
                cy = sum([p[1] for p in bbox]) / 4
                parsed_data.append({"text": text_clean, "raw_text": text, "x": cx, "y": cy})
            
            # 1. 체온계 숫자 인식 (35.0 ~ 42.9 사이의 숫자 패턴)
            for item in parsed_data:
                temp_match = re.search(r'(3[5-9]\.\d|4[0-2]\.\d)', item["text"])
                if temp_match:
                    temperature = temp_match.group()
            
            # 화면의 중앙 x, y값 대략적 계산 (좌우/상하 구분을 위해)
            if parsed_data:
                avg_x = sum([d["x"] for d in parsed_data]) / len(parsed_data)
                avg_y = sum([d["y"] for d in parsed_data]) / len(parsed_data)
                
                job_keywords = ["형틀", "철근", "콘크리트", "비계", "전기", "설비", "안전"]
                country_keywords = ["CHINA", "중국", "VIETNAM", "베트남", "MYANMAR", "미얀마", "외국인"]
                
                for item in parsed_data:
                    txt = item["text"]
                    raw_txt = item["raw_text"]
                    x, y = item["x"], item["y"]
                    
                    # 혈액형 (위치 상관없이 패턴으로 추출)
                    if re.search(r'(A|B|O|AB)형', txt, re.IGNORECASE):
                        blood_type = re.search(r'(A|B|O|AB)형', txt, re.IGNORECASE).group()
                    
                    # 국적 확인
                    for c in country_keywords:
                        if c in txt.upper():
                            nationality = raw_txt
                    
                    # 공종 확인
                    for j in job_keywords:
                        if j in txt:
                            job_type = j
                            
                    # 현장명 (우측 상단: x가 평균보다 크고, y가 평균보다 작음 / 또는 '자이', '건설' 등 포함)
                    if ("자이" in txt or "건설" in txt) and (x > avg_x):
                        site_name = raw_txt
                    elif "건설" in txt and (x < avg_x):
                        company = raw_txt # 좌측 상단 업체명
                        
                    # 이름 (우측 하단: x가 평균보다 크고 y가 평균보다 큼, 2~4글자 한글)
                    if x > avg_x and y > avg_y and re.fullmatch(r'^[가-힣]{2,4}$', txt):
                        # 현장명이나 기타 키워드가 아닐 때 이름으로 간주
                        if not any(k in txt for k in job_keywords + ["자이", "건설"]):
                            name = txt

            # 데이터 리스트에 추가
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
            
            # 기존 데이터프레임에 병합 및 저장
            st.session_state.df = pd.concat([st.session_state.df, new_data], ignore_index=True)
            st.session_state.df.to_csv(DATA_FILE, index=False, encoding='utf-8-sig')

st.divider()

# 누적된 데이터 리스트업 보여주기
st.subheader("📊 자동 저장된 데이터 리스트")
st.dataframe(st.session_state.df, use_container_width=True)

# 엑셀로 다운로드하는 버튼
csv = st.session_state.df.to_csv(index=False, encoding='utf-8-sig')
st.download_button(
    label="📥 엑셀(CSV) 파일로 다운로드",
    data=csv,
    file_name="현장_측정데이터.csv",
    mime="text/csv",
)
