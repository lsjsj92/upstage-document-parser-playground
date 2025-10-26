# project_path/frontend/app.py

import streamlit as st
import requests
import time
from pathlib import Path
import sys

# Add project root to Python path
current_dir = Path(__file__).parent
root_dir = current_dir.parent
sys.path.append(str(root_dir))

from frontend.components.file_uploader import FileUploader
from frontend.components.document_viewer import DocumentViewer
from frontend.utils.config import config

# Streamlit page configuration
st.set_page_config(
    page_title="Upstage Document Parser playground",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API endpoint
API_BASE_URL = f"http://localhost:{config.PORT}/api/v1"

class StreamlitApp:
    """
    Upstage Document Parser Playground의 메인 Streamlit 애플리케이션 클래스

    파일 업로드, 문서 리스트 조회, 문서 뷰어 등의 페이지를 관리합니다.
    """

    def __init__(self):
        """
        StreamlitApp을 초기화합니다.

        FileUploader, DocumentViewer 컴포넌트를 생성하고
        세션 상태를 초기화합니다.
        """
        self.file_uploader = FileUploader(API_BASE_URL)
        self.document_viewer = DocumentViewer(API_BASE_URL)

        # Session state initialization
        if 'selected_doc_id' not in st.session_state:
            st.session_state.selected_doc_id = None

    def run(self):
        """
        Streamlit 애플리케이션을 실행합니다.

        헤더, 사이드바 메뉴, 페이지 라우팅을 처리합니다.
        """
        # Header
        st.title("Upstage Document Parser playground")
        st.info("문의: https://www.linkedin.com/in/lsjsj92/")
        
        # Sidebar menu
        with st.sidebar:
            st.header("Menu")
            page = st.radio(
                "Select Page",
                [
                    "파일 업로드", 
                    "파싱된 문서 리스트", 
                    "문서 상세 뷰어"
                ]
            )
            
            # API status check
            self._render_api_status_sidebar()
        
        # Page routing
        if page == "파일 업로드":
            self._render_upload_page()
        elif page == "파싱된 문서 리스트":
            self._render_document_list()
        elif page == "문서 상세 뷰어":
            self._render_document_viewer()
    
    def _render_api_status_sidebar(self):
        """
        사이드바에 API 상태와 시스템 통계를 표시합니다.
        - API 연결 상태
        - Hybrid Parsing 및 OCR 기능 사용 가능 여부
        - 전체 문서 통계 (총 문서 수, 완료된 문서 수, OCR 향상 요소 등)
        """
        st.markdown("---")
        st.markdown("#### API Status")
        
        try:
            response = requests.get(f"{API_BASE_URL.replace('/api/v1', '')}/health", timeout=5)
            if response.status_code == 200:
                health_data = response.json()
                st.success("API Connected")
                
                if 'features' in health_data:
                    features = health_data['features']
                    if 'hybrid_parsing' in features:
                        st.success("Hybrid Parsing Available")
                    if 'ocr_text_extraction' in features:
                        st.success("OCR Text Extraction")
            else:
                st.error("API Error")
        except:
            st.error("API Connection Failed")
        
        try:
            response = requests.get(f"{API_BASE_URL}/analytics/summary", timeout=5)
            if response.status_code == 200:
                analytics = response.json()
                summary = analytics.get('summary', {})

                st.metric("Total Documents", summary.get('total_documents', 0))
                st.metric("Completed", summary.get('completed_documents', 0))
        except:
            pass
    
    def _render_upload_page(self):
        """
        파일 업로드 페이지를 렌더링합니다.
        - 파일 선택 및 업로드
        - 실시간 파싱 진행 상황 모니터링
        - 파싱 완료 후 결과 통계 표시
        """
        st.header("File Upload and Parsing")
        
        st.info("활용 가능한 파일: PDF, DOCX, PPTX, JPG, JPEG, PNG (Max 50MB)")
        st.markdown("**자동 기능**: 이미지 내 텍스트 추출")
        
        uploaded_file = st.file_uploader(
            "업로드 할 파일을 선택하세요.",
            type=['pdf', 'docx', 'pptx', 'jpg', 'jpeg', 'png'],
            accept_multiple_files=False
        )
        
        if uploaded_file:
            # File information
            col1, col2, col3 = st.columns(3)
            with col1:
                st.write(f"**File Name:** {uploaded_file.name}")
            with col2:
                st.write(f"**File Size:** {uploaded_file.size:,} bytes")
            with col3:
                st.write(f"**File Type:** {uploaded_file.type}")
            
            if st.button("파싱 시작", type="primary"):
                with st.spinner("파일 업로드 및 파싱을 시작합니다."):
                    success, result = self.file_uploader.upload_file(uploaded_file)
                    
                    if success:
                        st.success("파일 업로드 성공!")
                        
                        # Monitor parsing progress
                        self._monitor_parsing_progress(result['id'])
                    else:
                        st.error(f"업로드 실패: {result}")
    
    def _monitor_parsing_progress(self, doc_id: str):
        """
        문서 파싱 진행 상황을 실시간으로 모니터링합니다.
        - 2초마다 파싱 상태 확인
        - 진행 상황을 프로그레스 바로 표시
        - 완료/실패 시 결과 통계 표시

        Args:
            doc_id: 모니터링할 문서 ID
        """
        progress_container = st.container()
        
        with progress_container:
            progress_bar = st.progress(0)
            status_text = st.empty()
            stats_container = st.empty()
        
        for i in range(120):  # 4 minute timeout
            try:
                response = requests.get(f"{API_BASE_URL}/documents/{doc_id}")
                if response.status_code == 200:
                    doc_data = response.json()
                    status = doc_data['parsing_status']
                    
                    if status == "completed":
                        progress_bar.progress(100)
                        status_text.success("파싱 완료!")
                        
                        # Display parsing results
                        if doc_data.get('parsed_data'):
                            elements = doc_data['parsed_data'].get('elements', [])
                            pages = max([elem['page'] for elem in elements], default=0)
                            image_elements = [e for e in elements if e.get('base64_encoding')]
                            text_elements = [e for e in elements if e.get('content', {}).get('text')]
                            
                            with stats_container:
                                col1, col2, col3, col4 = st.columns(4)
                                with col1:
                                    st.metric("총 요소", len(elements))
                                with col2:
                                    st.metric("페이지", pages)
                                with col3:
                                    st.metric("이미지 요소", len(image_elements))
                                with col4:
                                    st.metric("텍스트 요소", len(text_elements))
                        
                        if st.button("문서 보기"):
                            st.session_state.selected_doc_id = doc_id
                            st.success("문서가 선택되었습니다. 문서 뷰어 탭으로 이동하세요.")
                        break
                        
                    elif status == "failed":
                        progress_bar.progress(0)
                        status_text.error(f"파싱 실패: {doc_data.get('error_message', 'Unknown error')}")
                        break
                    elif status == "processing":
                        progress_bar.progress(min(50 + i, 90))
                        status_text.info("파싱 진행 중")
                    else:
                        progress_bar.progress(min(i * 2, 30))
                        status_text.info("파싱 대기열에 추가됨")
                
                time.sleep(2)
                
            except Exception as e:
                status_text.error(f"상태 확인 오류: {str(e)}")
                break
    
    def _render_document_list(self):
        """
        파싱된 문서 리스트 페이지를 렌더링합니다.

        상태별 필터링, 정렬 기능을 제공하며 각 문서를 카드 형태로 표시합니다.
        """
        st.header("파싱된 문서 리스트")
        
        col1, col2 = st.columns([1, 1])
        with col1:
            status_filter = st.selectbox("상태 값 기반 필터", ["All", "Completed", "Processing", "Failed"])
        with col2:
            sort_by = st.selectbox("정렬", ["Upload Time", "File Name"])
        
        try:
            response = requests.get(f"{API_BASE_URL}/documents")
            if response.status_code == 200:
                documents = response.json()
                
                if status_filter != "All":
                    filter_map = {"Completed": "completed", "Processing": "processing", "Failed": "failed"}
                    documents = [d for d in documents if d['parsing_status'] == filter_map[status_filter]]
                
                if not documents:
                    st.info("조건에 맞는 문서가 없습니다.")
                    return
                
                if sort_by == "File Name":
                    documents.sort(key=lambda x: x['original_filename'])
                
                # Display document cards
                for i, doc in enumerate(documents):
                    self._render_document_card(doc, i)
                        
            else:
                st.error("문서 리스트를 불러올 수 없습니다.")
                
        except Exception as e:
            st.error(f"오류가 발생했습니다: {str(e)}")
    
    def _render_document_card(self, doc: dict, index: int):
        """
        개별 문서 카드를 렌더링합니다.

        Args:
            doc: 문서 데이터 딕셔너리
            index: 문서 인덱스 (고유 key 생성용)
        """
        status_colors = {
            "completed": "success",
            "processing": "info", 
            "failed": "error",
            "pending": "warning"
        }
        
        status_color = status_colors.get(doc['parsing_status'], 'info')
        
        with st.expander(f"{doc['original_filename']}", expanded=False):
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                st.markdown(f"**Status:** :{status_color}[{self._get_status_badge(doc['parsing_status'])}]")
                st.write(f"**Upload Time:** {doc['upload_time'][:19]}")
                st.write(f"**File Size:** {doc['file_size']:,} bytes")
                
                if doc['parsing_status'] == 'completed' and doc.get('parsed_data'):
                    elements = doc['parsed_data'].get('elements', [])
                    pages = max([elem['page'] for elem in elements], default=0)
                    image_elements = [e for e in elements if e.get('base64_encoding')]
                    
                    # Statistics
                    stats_col1, stats_col2, stats_col3 = st.columns(3)
                    with stats_col1:
                        st.metric("Elements", len(elements))
                    with stats_col2:
                        st.metric("Pages", pages)
                    with stats_col3:
                        st.metric("Images", len(image_elements))
            
            with col2:
                if doc['parsing_status'] == 'completed':
                    if st.button("View Document", key=f"view_{doc['id']}_{index}"):
                        st.session_state.selected_doc_id = doc['id']
                        st.success("문서가 선택되었습니다. 문서 뷰어 탭으로 이동하세요.")
                else:
                    st.button("Processing.", key=f"waiting_{doc['id']}_{index}", disabled=True)
            
            with col3:
                if st.button("Delete", key=f"delete_{doc['id']}_{index}", type="secondary"):
                    if self._delete_document(doc['id']):
                        st.success("문서가 삭제되었습니다.")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("문서 삭제에 실패했습니다.")
    
    def _render_document_viewer(self):
        """
        문서 뷰어 페이지를 렌더링합니다.

        완료된 문서 목록을 표시하고 선택한 문서의 상세 내용을 보여줍니다.
        """
        st.header("Document Viewer")
        st.markdown("좌표 보존 시각화 + 이미지 텍스트 추출 결과")
        
        # Document selection
        try:
            response = requests.get(f"{API_BASE_URL}/documents")
            if response.status_code == 200:
                documents = response.json()
                completed_docs = [doc for doc in documents if doc['parsing_status'] == 'completed']
                
                if not completed_docs:
                    st.warning("완료된 문서가 없습니다.")
                    return
                
                doc_options = {doc['original_filename']: doc['id'] for doc in completed_docs}
                
                # Check for pre-selected document
                selected_filename = None
                if st.session_state.selected_doc_id:
                    for filename, doc_id in doc_options.items():
                        if doc_id == st.session_state.selected_doc_id:
                            selected_filename = filename
                            break
                
                if not selected_filename and doc_options:
                    selected_filename = list(doc_options.keys())[0]
                
                selected_filename = st.selectbox(
                    "문서 선택", 
                    list(doc_options.keys()),
                    index=list(doc_options.keys()).index(selected_filename) if selected_filename else 0
                )
                
                if selected_filename:
                    doc_id = doc_options[selected_filename]
                    # Render document viewer
                    self.document_viewer.render_document(doc_id)
            else:
                st.error("문서 리스트를 불러올 수 없습니다.")
                
        except Exception as e:
            st.error(f"오류가 발생했습니다: {str(e)}")
    
    def _get_status_badge(self, status):
        """
        파싱 상태에 따른 배지 텍스트를 반환합니다.

        Args:
            status: 파싱 상태 문자열

        Returns:
            str: 표시할 배지 텍스트
        """
        badges = {
            "pending": "Pending",
            "processing": "Processing", 
            "completed": "Completed",
            "failed": "Failed"
        }
        return badges.get(status, status)
    
    def _delete_document(self, doc_id):
        """
        문서를 삭제합니다.

        Args:
            doc_id: 삭제할 문서의 ID

        Returns:
            bool: 삭제 성공 여부
        """
        try:
            response = requests.delete(f"{API_BASE_URL}/documents/{doc_id}")
            return response.status_code == 200
        except:
            return False

def main():
    """
    애플리케이션의 진입점입니다.

    StreamlitApp 인스턴스를 생성하고 실행합니다.
    """
    app = StreamlitApp()
    app.run()

if __name__ == "__main__":
    main()
    