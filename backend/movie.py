from typing import List, Optional
import os
import json

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field
from openai import OpenAI

from sqlmodel import (
    SQLModel,
    Field as SQLField,
    Relationship,
    Session,
    create_engine,
    select,
)


# -------------------------------
# DB 설정
# -------------------------------
DATABASE_URL = os.environ.get("DATABASE_URL")
# 배포환경에서 없으면 로컬 SQLite로 fallback
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./movie.db"

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)


def get_session():
    with Session(engine) as session:
        yield session


# -------------------------------
# DB 모델(SQLModel)
# -------------------------------
class MovieDB(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)

    name: str = SQLField(index=True, unique=True)
    director: str
    open_date: str
    genre: str
    poster_url: str

    comments: List["CommentDB"] = Relationship(back_populates="movie")


class CommentDB(SQLModel, table=True):
    id: Optional[int] = SQLField(default=None, primary_key=True)
    movie_id: int = SQLField(foreign_key="moviedb.id", index=True)

    user_name: str
    comment: str
    emotion: str = ""
    confidence_score: float = 0.0
    rate_score: int = SQLField(ge=1, le=5)

    movie: MovieDB = Relationship(back_populates="comments")


# -------------------------------
# API 스키마(Pydantic)
# -------------------------------
class CommentIn(BaseModel):
    movie_name: str
    user_name: str
    comment: str
    rate_score: int = Field(ge=1, le=5)


class CommentOut(BaseModel):
    movie_name: str
    user_name: str
    comment: str
    emotion: str
    confidence_score: float
    rate_score: int


class MovieIn(BaseModel):
    name: str
    director: str
    open_date: str
    genre: str
    poster_url: str
    comments: List[CommentOut] = []  # 프론트가 보내는 필드 호환용


class MovieOut(BaseModel):
    name: str
    director: str
    open_date: str
    genre: str
    poster_url: str
    comments: List[CommentOut] = []


# -------------------------------
# 감성 분석 모델
# -------------------------------
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def analyze_comment_with_openai(text: str) -> tuple[str, float]:
    """
    returns: (emotion_label, confidence_score)
    emotion_label: POSITIVE / NEUTRAL / NEGATIVE
    confidence_score: 0.0 ~ 1.0 (모델이 추정한 '자기확신' 값)
    """
    prompt = f"""
    당신은 감성 분석 전문가입니다.
    사용자의 영화 리뷰를 다음 감정 중 하나로 분류해 주세요.:
    POSITIVE, NEUTRAL, NEGATIVE.

    유효한 JSON 형식으로 응답해 주세요:
    - label: POSITIVE|NEUTRAL|NEGATIVE 중 하나
    - confidence: 0.0 부터 1.0 사이의 숫자 (모델의 확신 정도)

    Text: {text}
    """.strip()

    resp = client.responses.create(
        model="gpt-4o-mini",
        input=prompt,
    )
    # Responses API에서 텍스트만 추출
    out = resp.output_text().strip()

    # JSON 파싱(안전장치)
    try:
        data = json.loads(out)
        label = str(data.get("label", "NEUTRAL")).upper()
        confidence = float(data.get("confidence", 0.5))
        if label not in {"POSITIVE", "NEUTRAL", "NEGATIVE"}:
            label = "NEUTRAL"
        confidence = max(0.0, min(1.0, confidence))
        return label, confidence
    except Exception:
        # 모델이 JSON을 어겼을 때 fallback
        return "NEUTRAL", 0.5


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    # 테이블 생성 (운영에선 migration이 이상적이지만, 과제/프로토타입엔 충분)
    SQLModel.metadata.create_all(engine)
    yield
    print("Shutting down.")
    model = None


app = FastAPI(lifespan=lifespan)


def analyze_comment(text: str):
    result = model(text)[0]
    return result["label"], float(result["score"])


def to_movie_out(movie: MovieDB, session: Session) -> MovieOut:
    comments = session.exec(
        select(CommentDB).where(CommentDB.movie_id == movie.id)
    ).all()
    return MovieOut(
        name=movie.name,
        director=movie.director,
        open_date=movie.open_date,
        genre=movie.genre,
        poster_url=movie.poster_url,
        comments=[
            CommentOut(
                movie_name=movie.name,
                user_name=c.user_name,
                comment=c.comment,
                emotion=c.emotion,
                confidence_score=c.confidence_score,
                rate_score=c.rate_score,
            )
            for c in comments
        ],
    )


# -------------------------------
# 영화 API (기존 경로 유지)
# -------------------------------
@app.get("/movies/get", response_model=List[MovieOut])
def get_movies(session: Session = Depends(get_session)):
    movies = session.exec(select(MovieDB)).all()
    return [to_movie_out(m, session) for m in movies]


@app.post("/movies/add")
def add_movie(movie: MovieIn, session: Session = Depends(get_session)):
    exists = session.exec(select(MovieDB).where(MovieDB.name == movie.name)).first()
    if exists:
        raise HTTPException(status_code=400, detail="Movie already exists")

    m = MovieDB(
        name=movie.name,
        director=movie.director,
        open_date=movie.open_date,
        genre=movie.genre,
        poster_url=movie.poster_url,
    )
    session.add(m)
    session.commit()
    return {"message": "Movie added successfully"}


@app.delete("/movies/delete/{movie_name}")
def delete_movie(movie_name: str, session: Session = Depends(get_session)):
    movie = session.exec(select(MovieDB).where(MovieDB.name == movie_name)).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    comments = session.exec(
        select(CommentDB).where(CommentDB.movie_id == movie.id)
    ).all()
    for c in comments:
        session.delete(c)

    session.delete(movie)
    session.commit()
    return {"message": "Movie deleted successfully"}


# -------------------------------
# 댓글 API (기존 경로 유지)
# -------------------------------
@app.post("/movies/comments/add")
async def add_comment(comment: CommentIn, session: Session = Depends(get_session)):
    movie = session.exec(
        select(MovieDB).where(MovieDB.name == comment.movie_name)
    ).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    emotion, score = analyze_comment_with_openai(comment.comment)

    c = CommentDB(
        movie_id=movie.id,
        user_name=comment.user_name,
        comment=comment.comment,
        rate_score=comment.rate_score,
        emotion=emotion,
        confidence_score=score,
    )
    session.add(c)
    session.commit()
    return {"message": "Comment added successfully"}


@app.delete("/movies/comments/delete/{movie_name}/{user_name}")
async def delete_comment(
    movie_name: str, user_name: str, session: Session = Depends(get_session)
):
    movie = session.exec(select(MovieDB).where(MovieDB.name == movie_name)).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    target = session.exec(
        select(CommentDB).where(
            CommentDB.movie_id == movie.id, CommentDB.user_name == user_name
        )
    ).first()
    if not target:
        raise HTTPException(status_code=404, detail="Comment not found")

    session.delete(target)
    session.commit()
    return {"message": "Comment deleted successfully"}


@app.post("/movies/comments/{movie_name}/average_score")
async def compute_average_rating(
    movie_name: str, session: Session = Depends(get_session)
):
    movie = session.exec(select(MovieDB).where(MovieDB.name == movie_name)).first()
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")

    comments = session.exec(
        select(CommentDB).where(CommentDB.movie_id == movie.id)
    ).all()
    if len(comments) == 0:
        return {"average_rate_score": 0.0, "average_confidence_score": 0.0}

    avg_rate = sum(c.rate_score for c in comments) / len(comments)
    avg_conf = sum(c.confidence_score for c in comments) / len(comments)
    return {"average_rate_score": avg_rate, "average_confidence_score": avg_conf}


if __name__ == "__main__":
    import os
    import uvicorn

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8000"))  # 플랫폼이 주는 PORT 우선
    uvicorn.run("movie:app", host=host, port=port)
