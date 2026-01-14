from pydantic import BaseModel
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import Field
from contextlib import asynccontextmanager
from transformers import pipeline


class Comment(BaseModel):
    movie_name: str
    user_name: str
    comment: str
    emotion: str = ""
    confidence_score: float = 0.0
    rate_score: int = Field(ge=1, le=5)


class Movie(BaseModel):
    name: str
    director: str
    open_date: str
    genre: str
    poster_url: str
    comments: List[Comment] = []


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


app = FastAPI(lifespan=lifespan)


@app.get("/movies/get")
def get_movies():
    return movie_db


@app.post("/movies/add")
def add_movie(movie: Movie):
    movie_db.append(movie)
    return {"message": "Movie added successfully"}


@app.delete("/movies/delete/{movie_name}")
def delete_movie(movie_name: str):
    global movie_db

    movie_db = [movie for movie in movie_db if movie.name != movie_name]
    return {"message": "Movie deleted successfully"}


def analyze_comment(comment: str):
    result = model(comment)[0]
    label = result["label"]
    score = result["score"]
    return label, score


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


@app.delete("/movies/comments/delete/{movie_name}/{user_name}")
async def delete_comment(movie_name: str, user_name: str):
    for movie in movie_db:
        if movie.name == movie_name:
            movie.comments = [
                comment for comment in movie.comments if comment.user_name != user_name
            ]
            return {"message": "Comment deleted successfully"}
    raise HTTPException(status_code=404, detail="Movie not found")


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
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
