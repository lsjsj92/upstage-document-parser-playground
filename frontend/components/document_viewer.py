# project_path/frontend/components/document_viewer.py
import streamlit as st
import requests
from typing import Dict, Any, List
import base64
from io import BytesIO
from PIL import Image, ImageDraw
from pathlib import Path
import sys

# 프로젝트 루트 경로 추가
current_dir = Path(__file__).parent
root_dir = current_dir.parent.parent
sys.path.append(str(root_dir))

class DocumentViewer:
    def __init__(self, api_base_url: str):
        self.api_base_url = api_base_url
    
    def render_document(self, doc_id: str):
        """
        문서 뷰어를 렌더링합니다.
        - 문서 정보 및 파싱 통계 표시
        - 페이지별 보기 지원
        - 좌표 기반 레이아웃, 바운딩 박스 시각화, 요소 상세 정보 탭 제공

        Args:
            doc_id: 표시할 문서의 ID
        """
        try:
            # Fetch base document data first
            doc_response = requests.get(f"{self.api_base_url}/documents/{doc_id}")
            doc_response.raise_for_status()
            doc_data = doc_response.json()
            
            if doc_data['parsing_status'] != 'completed':
                st.warning("문서 파싱이 아직 완료되지 않았습니다.")
                return

            # 전체 페이지 수 계산
            total_pages = 0
            if doc_data.get('parsed_data') and doc_data['parsed_data'].get('elements'):
                pages = [elem['page'] for elem in doc_data['parsed_data']['elements']]
                if pages:
                    total_pages = max(pages)

            if total_pages == 0:
                st.warning("문서에서 페이지를 찾을 수 없습니다.")
                return
            
            selected_page = st.selectbox(
                "페이지 선택",
                list(range(1, total_pages + 1)),
                format_func=lambda x: f"Page {x}"
            )

            self._render_enhanced_main_view_with_hybrid(doc_data, selected_page)
            
        except requests.exceptions.RequestException as e:
            st.error(f"API 서버에서 문서를 불러오는 데 실패했습니다: {e}")
        except Exception as e:
            st.error(f"문서 뷰어 렌더링 중 오류 발생: {str(e)}")

    def _render_enhanced_main_view_with_hybrid(self, doc_data: Dict[str, Any], page_num: int):
        """
        Hybrid parsing 결과를 포함한 메인 뷰를 렌더링합니다.
        - 탭 1: 좌표 기반 문서 레이아웃 재구성 + 전체 HTML 렌더링
        - 탭 2: 바운딩 박스 시각화 (OCR 향상 요소 강조)
        - 탭 3: 요소 상세 정보 (필터링 가능)

        Args:
            doc_data: 문서 데이터
            page_num: 현재 페이지 번호
        """
        page_elements = []
        if doc_data.get('parsed_data'):
             page_elements = [elem for elem in doc_data['parsed_data']['elements'] if elem['page'] == page_num]

        if not page_elements:
            st.warning(f"{page_num}페이지에서 요소를 찾을 수 없습니다.")
            return
        
        st.header(f"페이지 {page_num} 상세 분석")
        
        tab_titles = [
            "문서 레이아웃", 
            "바운딩 박스 시각화", 
            "요소 상세 정보",
        ]
        tab1, tab2, tab3 = st.tabs(tab_titles)

        with tab1:
            st.markdown("#### 좌표 기반 문서 레이아웃 재구성")
            st.info("각 요소의 위치와 크기를 원본 문서와 유사하게 시각적으로 재구성한 결과입니다.")
            self._render_coordinate_preserved_content_with_hybrid(page_elements)

            st.markdown("---")
            st.markdown("#### 페이지 전체 HTML 렌더링 (읽기 순서 기준)")
            st.info("페이지 내 모든 요소의 HTML 콘텐츠를 순서대로 합쳐 렌더링한 결과입니다.")
            
            page_html_content = self._generate_page_html(page_elements)
            st.components.v1.html(page_html_content, height=600, scrolling=True)

        with tab2:
            self._render_visual_with_bounding_boxes_hybrid(page_elements, page_num)

        with tab3:
            self._render_element_details_with_hybrid(page_elements)

    def _render_coordinate_preserved_content_with_hybrid(self, elements: List[Dict[str, Any]]):
        """
        좌표 기반 콘텐츠를 렌더링합니다.
        원본 문서의 레이아웃을 최대한 보존하여 HTML로 재구성합니다.

        Args:
            elements: 페이지 요소 리스트
        """
        try:
            coordinate_html = self._generate_coordinate_preserved_html_with_hybrid(elements)
            st.components.v1.html(coordinate_html, height=850, scrolling=True)
        except Exception as e:
            st.error(f"좌표 기반 콘텐츠 렌더링 오류: {str(e)}")

    def _generate_coordinate_preserved_html_with_hybrid(self, elements: List[Dict[str, Any]]) -> str:
        """
        좌표 정보를 활용하여 원본 문서 레이아웃을 재현하는 HTML을 생성합니다.
        - 각 요소를 절대 위치(absolute position)로 배치
        - OCR 향상 요소는 녹색 테두리로 강조 표시
        - 이미지 요소의 경우 추출된 텍스트도 함께 표시

        Args:
            elements: 문서 요소 리스트

        Returns:
            str: 렌더링 가능한 HTML 문자열
        """
        html_elements = []
        for elem in elements:
            coordinates = elem.get('coordinates', [])
            if not (coordinates and isinstance(coordinates, list) and len(coordinates) >= 4):
                continue

            try:
                top_left, _, bottom_right, _ = coordinates
                left, top = top_left.get('x', 0) * 100, top_left.get('y', 0) * 100
                width = (bottom_right.get('x', 0) - top_left.get('x', 0)) * 100
                height = (bottom_right.get('y', 0) - top_left.get('y', 0)) * 100

                if width <= 0 or height <= 0: continue

                content = elem.get('content', {})
                base64_data = elem.get('base64_encoding')
                ocr_enhanced = elem.get('ocr_enhanced', False)
                
                border_style = "2px solid #28a745" if ocr_enhanced else "1px solid rgba(0,0,0,0.1)"
                
                inner_html = ""
                if base64_data:
                    mime_type = elem.get('image_mime_type', 'image/png')
                    ocr_badge = '<div class="ocr-badge">OCR Enhanced</div>' if ocr_enhanced else ''
                    
                    # NEW LOGIC: Check for OCR text and append it
                    ocr_text_html = ''
                    if ocr_enhanced and content.get('text'):
                        ocr_text_html = f'''
                        <div class="ocr-text-wrapper">
                            <div class="ocr-text-header">Extracted Text</div>
                            <pre class="ocr-text-content">{content['text']}</pre>
                        </div>
                        '''

                    inner_html = f'''
                    <div class="image-wrapper">
                        <img src="data:{mime_type};base64,{base64_data}" style="width:100%; height:auto; object-fit: contain;"/>
                        {ocr_badge}
                    </div>
                    {ocr_text_html}
                    '''
                elif content.get('html'):
                    inner_html = f'<div class="content-wrapper">{content["html"]}</div>'
                else:
                    inner_html = f'<div class="content-wrapper"><p>{content.get("text", "")}</p></div>'

                style = (f'position: absolute; left: {left:.4f}%; top: {top:.4f}%; '
                         f'width: {width:.4f}%; height: {height:.4f}%; border: {border_style}; '
                         f'display: flex; flex-direction: column; overflow: hidden;')
                
                html_elements.append(f'<div style="{style}">{inner_html}</div>')
            except (KeyError, IndexError, TypeError):
                continue
        
        return f"""
        <!DOCTYPE html><html><head><title>Hybrid Parsed Document Preview</title><meta charset="UTF-8">
        <style>
            body {{ margin: 0; font-family: sans-serif; background-color: #f0f2f6; }}
            .page-container {{
                position: relative; width: 100%; max-width: 800px; margin: 20px auto; 
                border: 1px solid #ccc; background-color: white; aspect-ratio: 1 / 1.414; 
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }}
            .page-container * {{ box-sizing: border-box; }}
            .content-wrapper {{ width: 100%; height: 100%; padding: 1% 2%; overflow: auto; font-size: 1.5vw; line-height: 1.2; }}
            .image-wrapper {{ position: relative; flex-shrink: 0; }}
            .ocr-badge {{
                position: absolute; top: 2px; right: 2px; background: #28a745; color: white;
                font-size: 10px; padding: 2px 4px; border-radius: 3px; z-index: 10;
            }}
            .ocr-text-wrapper {{ 
                flex-grow: 1; overflow-y: auto; background-color: #f8f9fa; border-top: 1px solid #dee2e6;
            }}
            .ocr-text-header {{
                font-size: 11px; font-weight: bold; color: #495057; background-color: #e9ecef;
                padding: 2px 5px;
            }}
            pre.ocr-text-content {{
                white-space: pre-wrap; word-wrap: break-word; font-size: 10px; margin: 0; padding: 5px;
            }}
        </style></head><body>
        <div class="page-container">{''.join(html_elements)}</div>
        </body></html>"""
    
    def _render_visual_with_bounding_boxes_hybrid(self, elements: List[Dict[str, Any]], page_num: int):
        """
        문서 요소들의 바운딩 박스를 시각화합니다.
        - 카테고리별로 다른 색상 사용
        - OCR 향상 요소는 두꺼운 테두리와 [OCR] 라벨로 표시
        - 범례를 통해 카테고리 색상 안내

        Args:
            elements: 페이지 요소 리스트
            page_num: 현재 페이지 번호
        """
        try:
            canvas_width, canvas_height = 800, int(800 * 1.414)
            img = Image.new('RGB', (canvas_width, canvas_height), 'white')
            draw = ImageDraw.Draw(img)
            
            # Enhanced category colors with OCR indication
            category_colors = {
                'heading1': '#e74c3c', 'heading2': '#c0392b', 'paragraph': '#3498db', 
                'table': '#e67e22', 'figure': '#27ae60', 'chart': '#f39c12', 
                'list': '#9b59b6', 'footer': '#95a5a6', 'header': '#34495e', 
                'unknown': '#bdc3c7', 'composite_table': '#8e44ad'
            }
            
            for elem in elements:
                coordinates = elem.get('coordinates', [])
                if not (coordinates and isinstance(coordinates, list) and len(coordinates) >= 4): 
                    continue
                
                category = elem.get('category', 'unknown')
                elem_id = elem.get('id', '')
                has_image = bool(elem.get('base64_encoding'))
                ocr_enhanced = elem.get('ocr_enhanced', False)
                
                top_left, _, bottom_right, _ = coordinates
                left = top_left.get('x', 0) * canvas_width
                top = top_left.get('y', 0) * canvas_height
                right = bottom_right.get('x', 0) * canvas_width
                bottom = bottom_right.get('y', 0) * canvas_height
                
                if right <= left or bottom <= top: 
                    continue
                
                color = category_colors.get(category, '#95a5a6')
                
                # Different line styles for OCR enhanced elements
                line_width = 4 if ocr_enhanced else (3 if has_image else 2)
                
                draw.rectangle([left, top, right, bottom], outline=color, width=line_width)
                
                # Add OCR indicator
                label = f"{category} ({elem_id})"
                if ocr_enhanced:
                    label += " [OCR]"
                
                try:
                    bbox = draw.textbbox((left, top - 12), label)
                    bg_color = '#28a745' if ocr_enhanced else color
                    draw.rectangle(bbox, fill=bg_color)
                    draw.text((left, top - 12), label, fill='white')
                except AttributeError:
                    text_color = '#28a745' if ocr_enhanced else color
                    draw.text((left, top - 12), label, fill=text_color)
            
            st.image(img, caption=f"페이지 {page_num} - 바운딩 박스 시각화", use_container_width=True)
            
            legend_items = []
            for cat, color in category_colors.items():
                legend_items.append(f"<span style='background-color:{color};color:white;padding:2px 5px;border-radius:3px;'>{cat}</span>")
            
            legend_html = " | ".join(legend_items)
            st.markdown(f"**범례:** {legend_html}", unsafe_allow_html=True)
            
        except Exception as e:
            st.error(f"바운딩 박스 렌더링 오류: {str(e)}")

    def _generate_page_html(self, elements: List[Dict[str, Any]]) -> str:
        """
        페이지의 모든 요소 HTML을 읽기 순서대로 합쳐서 하나의 HTML 문자열로 만듭니다.

        Args:
            elements: 페이지 요소 리스트

        Returns:
            str: 통합된 HTML 문자열
        """
        # y 좌표(top) 기준으로 정렬하여 읽기 순서를 맞춤
        sorted_elements = sorted(
            elements,
            key=lambda e: e.get('coordinates', [{}])[0].get('y', 0)
        )
        
        # 각 요소의 HTML을 리스트에 추가
        html_parts = [
            elem.get('content', {}).get('html', '') for elem in sorted_elements
        ]
        
        # 전체를 감싸는 스타일 추가
        full_html = f"""
        <body style="margin: 0; padding: 0;">
            <div style="font-family: sans-serif; border: 1px solid #ddd; padding: 20px; background-color: #fff; margin: 10px;">
                {'<br>'.join(html_parts)}
            </div>
        </body>
        """
        return full_html

    def _render_element_details_with_hybrid(self, elements: List[Dict[str, Any]]):
        """
        페이지 내 모든 요소의 상세 정보를 렌더링합니다.
        - OCR 향상 요소만 보기 옵션
        - 이미지 요소만 보기 옵션
        - 각 요소의 텍스트, HTML, 이미지, 좌표 정보 제공

        Args:
            elements: 페이지 요소 리스트
        """
        st.info("추출된 데이터를 상세히 확인하세요.")

        # 필터 옵션
        col1, col2 = st.columns(2)
        with col1:
            show_only_ocr = st.checkbox("OCR 향상 요소만 표시", value=False)
        with col2:
            show_only_images = st.checkbox("이미지 요소만 표시", value=False)
        
        filtered_elements = elements
        if show_only_ocr:
            filtered_elements = [elem for elem in filtered_elements if elem.get('ocr_enhanced', False)]
        if show_only_images:
            filtered_elements = [elem for elem in filtered_elements if elem.get('base64_encoding')]
        
        if not filtered_elements:
            st.warning("필터 조건에 맞는 요소가 없습니다.")
            return
        
        for i, elem in enumerate(sorted(filtered_elements, key=lambda x: x.get('id', 0))):
            self._render_single_element_card_with_hybrid(elem, i)

    def _render_single_element_card_with_hybrid(self, element: Dict[str, Any], index: int):
        """
        개별 요소의 상세 정보를 카드 형태로 렌더링합니다.
        - 좌측: 페이지 번호, OCR 상태, 바운딩 박스, 이미지
        - 우측: 텍스트 콘텐츠, HTML 콘텐츠, 텍스트 통계

        Args:
            element: 요소 데이터
            index: 요소 인덱스 (고유 key 생성용)
        """
        category = element.get('category', 'unknown')
        elem_id = element.get('id', 'N/A')
        ocr_enhanced = element.get('ocr_enhanced', False)
        
        title_suffix = " [OCR Enhanced]" if ocr_enhanced else ""
        title = f"**{category.upper()}** (ID: {elem_id}){title_suffix}"
        
        with st.expander(title, expanded=False):
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.write(f"**페이지:** {element.get('page', 'N/A')}")
                st.write(f"**OCR 향상:** {'적용됨' if ocr_enhanced else '미적용'}")
                
                if element.get('coordinates'):
                    bbox = self._calculate_bounding_box(element['coordinates'])
                    st.write("**바운딩 박스:**")
                    st.json({k: f"{v:.4f}" for k, v in bbox.items()}, expanded=False)
                
                if element.get('base64_encoding'):
                    try:
                        image_data = base64.b64decode(element['base64_encoding'])
                        image = Image.open(BytesIO(image_data))
                        caption = f"Image (ID: {elem_id})"
                        if ocr_enhanced:
                            caption += " - OCR Enhanced"
                        st.image(image, caption=caption, use_container_width=True)
                    except Exception: 
                        st.error("이미지를 불러오는데 실패했습니다.")
            
            with col2:
                content = element.get('content', {})
                st.write("**텍스트 콘텐츠**")
                text_content = content.get('text', 'N/A')
                
                if ocr_enhanced and text_content != 'N/A':
                    st.success("OCR로 추출된 텍스트:")
                
                st.text_area(
                    "Text", 
                    value=text_content, 
                    height=120, 
                    disabled=True, 
                    key=f"text_{elem_id}_{index}"
                )
                
                if text_content != 'N/A':
                    st.write(f"**텍스트 길이:** {len(text_content)}자")
                    st.write(f"**단어 수:** {len(text_content.split())}개")
                
                st.write("**HTML 콘텐츠**")
                html_content = content.get('html', 'N/A')
                if html_content != 'N/A':
                    st.code(html_content, language='html')
                else:
                    st.text("HTML 콘텐츠 없음")

    def _calculate_bounding_box(self, coordinates: List[Dict[str, float]]) -> Dict[str, float]:
        """
        좌표 목록으로부터 바운딩 박스를 계산합니다.

        Args:
            coordinates: 좌표 리스트 [{'x': ..., 'y': ...}, ...]

        Returns:
            Dict: left, top, right, bottom, width, height 정보를 담은 딕셔너리
        """
        if not (coordinates and isinstance(coordinates, list)):
            return {}
        x = [c.get('x', 0) for c in coordinates]
        y = [c.get('y', 0) for c in coordinates]
        left, right, top, bottom = min(x), max(x), min(y), max(y)
        return {
            'left': left, 'top': top, 'right': right, 'bottom': bottom, 
            'width': abs(right - left), 'height': abs(bottom - top)
        }