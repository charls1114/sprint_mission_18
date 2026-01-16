import streamlit as st
from requests import get, post, delete
from PIL import Image
import time


BACKEND_BASE_URL = st.secrets.get("BACKEND_BASE_URL")
if not BACKEND_BASE_URL:
    st.error("BACKEND_BASE_URL이 설정되지 않았습니다. Streamlit Secrets에 등록하세요.")
    st.stop()

st.title("영화 평론 리뷰 모음 앱")
# 사이드바: 영화 추가 및 삭제
with st.sidebar:
    # 사이드바: 영화 추가
    st.header("영화 추가하기")
    name = st.text_input("영화 이름")
    director = st.text_input("감독")
    open_date = st.text_input("개봉일 (예: 2023-01-01)")
    genre = st.text_input("장르")
    poster_url = st.text_input("포스터 URL")

    if st.button("영화 추가"):
        movie_add_response = post(
            f"{BACKEND_BASE_URL}/movies/add",
            json={
                "name": name,
                "director": director,
                "open_date": open_date,
                "genre": genre,
                "poster_url": poster_url,
                "comments": [],
            },
        )
        if movie_add_response.status_code == 200:
            st.success("영화가 성공적으로 추가되었습니다!")
            time.sleep(1)
            st.rerun()
        else:
            st.error(
                "다음과 같은 이유로 영화 추가에 실패했습니다: "
                + movie_add_response.text
            )
    # 사이드바: 영화 삭제
    st.header("영화 삭제하기")
    del_name = st.text_input("삭제할 영화 이름")
    if st.button("영화 삭제"):
        movie_del_response = delete(f"{BACKEND_BASE_URL}/movies/delete/{del_name}")
        if movie_del_response.status_code == 200:
            st.success("영화가 성공적으로 삭제되었습니다!")
            time.sleep(1)
            st.rerun()
        else:
            st.error(
                "다음과 같은 이유로 영화 삭제에 실패했습니다: "
                + movie_del_response.text
            )

# 영화 목록 불러오기
movie_get_response = get(f"{BACKEND_BASE_URL}/movies/get")
if movie_get_response.status_code != 200:
    st.error(
        "다음과 같은 이유로 영화 목록 불러오기에 실패했습니다: "
        + movie_get_response.text
    )
movies = movie_get_response.json()

# 메인 페이지: 영화 목록 및 리뷰 작성/조회
if len(movies) == 0:
    # 영화가 하나도 없을 때
    st.warning("등록된 영화가 없습니다. 사이드바에서 영화를 추가해 주세요.")
else:
    with st.expander(label="영화 목록", icon="🎬", expanded=True):
        for movie in movies:
            # 영화 별 리뷰 섹션
            col1, col2 = st.columns([1, 2])
            with col1:
                st.subheader(movie["name"])
                try:
                    img = Image.open(get(movie["poster_url"], stream=True).raw)
                    st.image(img, width=200)
                except Exception as e:
                    st.error(f"포스터 이미지를 불러올 수 없습니다: {e}")
                st.markdown(f"###### 감독: {movie['director']}")
                st.markdown(f"###### 개봉일: {movie['open_date']}")
                st.markdown(f"###### 장르: {movie['genre']}")
            with col2:
                # 리뷰 작성 폼
                with st.form(key=f"comment_form_{movie['name']}"):
                    user_name = st.text_input(
                        "작성자 이름을 입력해 주세요",
                        key=f"user_name_input_{movie['name']}",
                    )
                    rate_score = st.slider(
                        "평점을 매겨주세요",
                        min_value=1,
                        max_value=5,
                        key=f"rate_score_slider_{movie['name']}",
                    )
                    comment = st.text_input(
                        "리뷰를 작성해 주세요",
                        key=f"comment_input_{movie['name']}",
                    )
                    if st.form_submit_button(label="리뷰 등록"):
                        with st.spinner("리뷰를 등록하는 중입니다..."):
                            response = post(
                                f"{BACKEND_BASE_URL}/movies/comments/add",
                                json={
                                    "movie_name": movie["name"],
                                    "user_name": user_name,
                                    "rate_score": rate_score,
                                    "comment": comment,
                                },
                            )
                        if response.status_code == 200:
                            st.success("리뷰가 성공적으로 등록되었습니다!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(
                                "다음과 같은 이유로 리뷰 제출에 실패했습니다: "
                                + response.text
                            )

                # 영화 리뷰 목록
                with st.container(border=True, height=180):
                    if len(movie["comments"]) == 0:
                        # 리뷰가 하나도 없을 때
                        st.markdown("**등록된 리뷰가 없습니다.**")
                    else:
                        # 평균 평점 및 신뢰도 점수 표시
                        st.markdown(f"**{movie['name']} 평균 평점**")
                        comment_score_response = post(
                            f"{BACKEND_BASE_URL}/movies/comments/{movie['name']}/average_score"
                        )
                        if comment_score_response.status_code != 200:
                            st.error(
                                "다음과 같은 이유로 평균 평점 불러오기에 실패했습니다: "
                                + comment_score_response.text
                            )
                            continue
                        else:
                            average_score = comment_score_response.json()
                            st.progress(
                                average_score["average_rate_score"] / 5,
                                text=f"영화 평점: {average_score['average_rate_score']:.2f}/5",
                            )
                            st.progress(
                                average_score["average_confidence_score"] / 1,
                                text=f"감성 분석 신뢰도 평균: {average_score['average_confidence_score']:.2f}",
                            )
                        # 리뷰 목록 표시
                        st.markdown(
                            f"**{movie['name']} 리뷰** {len(movie['comments'])}명 참여"
                        )
                        with st.container(border=True, height=300):
                            for i, comment in enumerate(movie["comments"][:10]):
                                with st.container(border=True):
                                    st.markdown(f"작성자: {comment['user_name']}")
                                    st.progress(
                                        comment["rate_score"] / 5,
                                        text=f"평점: {comment['rate_score']}/5",
                                    )
                                    st.markdown(f"{comment['comment']}")
                                    st.markdown(
                                        f"감성 분석 결과: **{comment['emotion']}**"
                                    )
                                    st.markdown(
                                        f"신뢰도 점수: {comment['confidence_score']:.2f}"
                                    )
                                    if st.button(
                                        "리뷰 삭제",
                                        key=f"delete_comment_{movie['name']}_{i}",
                                    ):
                                        delete_response = delete(
                                            f"{BACKEND_BASE_URL}/movies/comments/delete/{movie['name']}/{comment['user_name']}"
                                        )
                                        if delete_response.status_code == 200:
                                            st.success(
                                                "리뷰가 성공적으로 삭제되었습니다!"
                                            )
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            st.error(
                                                "다음과 같은 이유로 리뷰 삭제에 실패했습니다: "
                                                + delete_response.text
                                            )
            st.markdown("---")
