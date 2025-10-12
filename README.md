# 업스테이지 Document parser playground

# 설명 블로그
- [브롤그 url](https://lsjsj92.tistory.com/703)

# 실행 예시 이미지

![info](asset/parsing_result.png)
![info](asset/parsing_result_table.png)

# 필요한 것

## 1. 업스테이지 콘솔에 접속하여 API Key 할당 받기

## 2. 필요한 파이썬 라이브러리 설치(requrirements.txt)

# 파일 구조

.
├── LICENSE
├── README.md
├── .env.tmp (.env 파일로 변경)
├── asset
├── backend
│   ├── __init__.py
│   ├── config.py
│   ├── main.py
│   ├── models
│   │   ├── __init__.py
│   │   └── document.py
│   ├── routers
│   │   ├── __init__.py
│   │   └── routes.py
│   ├── services
│   │   ├── __init__.py
│   │   ├── file_processor.py
│   │   ├── storage.py
│   │   └── upstage_client.py
│   └── utils
│       ├── __init__.py
│       └── helpers.py
├── frontend
│   ├── __init__.py
│   ├── app.py
│   ├── components
│   │   ├── __init__.py
│   │   ├── document_viewer.py
│   │   ├── element_viewer.py
│   │   └── file_uploader.py
│   └── utils
│       ├── __init__.py
│       └── config.py
├── requirements.txt

# 실행 방법

# 터미널 1: python -m uvicorn backend.main:app --reload
# 터미널 2: streamlit run frontend/app.py
