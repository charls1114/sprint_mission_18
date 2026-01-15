from pydantic import BaseModel
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import Field
from contextlib import asynccontextmanager
from transformers import pipeline

# -------------------------------
# 데이터 모델 정의
# -------------------------------


# 댓글 모델
class Comment(BaseModel):
    movie_name: str
    user_name: str
    comment: str
    emotion: str = ""
    confidence_score: float = 0.0
    rate_score: int = Field(ge=1, le=5)


# 영화 모델
class Movie(BaseModel):
    name: str
    director: str
    open_date: str
    genre: str
    poster_url: str
    comments: List[Comment] = []


# -------------------------------
# 임시 데이터베이스 및 감성 분석 모델 로딩
# -------------------------------
model = None
movie_db: List[Movie] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("감성 모델 로딩 중...")
    global model
    model = pipeline(
        "sentiment-analysis", model="tabularisai/multilingual-sentiment-analysis"
    )
    print("감성 모델 로딩 완료!")
    yield
    print("Shutting down...")
    model = None


# -------------------------------
# FastAPI 애플리케이션 및 엔드포인트 정의
# -------------------------------
app = FastAPI(lifespan=lifespan)


# -------------------------------
# 영화 관련 API 엔드포인트
# -------------------------------


# 영화 목록 조회 API 엔드포인트
@app.get("/movies/get")
def get_movies():
    return movie_db


# 영화 추가 API 엔드포인트
@app.post("/movies/add")
def add_movie(movie: Movie):
    movie_db.append(movie)
    return {"message": "Movie added successfully"}


# 영화 삭제 API 엔드포인트
@app.delete("/movies/delete/{movie_name}")
def delete_movie(movie_name: str):
    global movie_db

    movie_db = [movie for movie in movie_db if movie.name != movie_name]
    return {"message": "Movie deleted successfully"}


# -------------------------------
# 댓글 관련 API 엔드포인트
# -------------------------------


# 감성 분석 함수
def analyze_comment(comment: str):
    result = model(comment)[0]
    label = result["label"]
    score = result["score"]
    return label, score


# 댓글 추가 API 엔드포인트
@app.post("/movies/comments/add")
async def add_comment(comment: Comment):
    for movie in movie_db:
        if movie.name == comment.movie_name:
            emotion, score = analyze_comment(comment.comment)
            comment.emotion = emotion
            comment.confidence_score = score
            movie.comments.append(comment)
            return {"message": "Comment added successfully"}
    raise HTTPException(status_code=404, detail="Movie not found")


# 댓글 삭제 API 엔드포인트
@app.delete("/movies/comments/delete/{movie_name}/{user_name}")
async def delete_comment(movie_name: str, user_name: str):
    for movie in movie_db:
        if movie.name == movie_name:
            movie.comments = [
                comment for comment in movie.comments if comment.user_name != user_name
            ]
            return {"message": "Comment deleted successfully"}
    raise HTTPException(status_code=404, detail="Movie not found")


# 평균 평점 계산 API 엔드포인트
@app.post("/movies/comments/{movie_name}/average_score")
async def compute_average_rating(movie_name: str):
    for movie in movie_db:
        if movie.name == movie_name:
            if len(movie.comments) == 0:
                return {"average_rate_score": 0.0, "average_confidence_score": 0.0}
            total_rating = sum(comment.rate_score for comment in movie.comments)
            average_rating = total_rating / len(movie.comments)
            total_confidence = sum(
                comment.confidence_score for comment in movie.comments
            )
            average_confidence = total_confidence / len(movie.comments)

            return {
                "average_rate_score": average_rating,
                "average_confidence_score": average_confidence,
            }
    raise HTTPException(status_code=404, detail="Movie not found")


if __name__ == "__main__":
    import os
    import uvicorn

    host = "127.0.0.1"
    port = int(os.environ.get("PORT", "8000"))  # 플랫폼이 주는 PORT 우선
    uvicorn.run("movie:app", host=host, port=port)
