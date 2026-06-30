import json
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, Column, Integer, String, Text, JSON, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

from config.settings import app_settings
from config.logger import get_logger

logger = get_logger(__name__)

Base = declarative_base()

class Article(Base):
    """SQLAlchemy model for the articles table."""
    __tablename__ = "articles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    domain = Column(String(50), nullable=False, index=True)
    topic = Column(String(255), nullable=False)
    subtopics = Column(Text, default="")
    title = Column(String(255), nullable=False)
    description = Column(Text, default="")
    content = Column(Text, nullable=False)  # Stores the full raw markdown text
    date = Column(String(20), nullable=False)  # Format: YYYY-MM-DD
    tags = Column(JSON, default=list)  # List of string tags
    read_time = Column(String(20), nullable=False)
    slug = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the article model to a dictionary representation matching the original JSON structure."""
        return {
            "id": self.slug,
            "category": self.domain,
            "topic": self.topic,
            "subtopics": self.subtopics,
            "title": self.title,
            "description": self.description,
            "date": self.date,
            "tags": self.tags,
            "readTime": self.read_time,
            "file": f"db://articles/{self.slug}",
            "content": self.content
        }

# Create Engine & Sessionmaker
DATABASE_URL = app_settings.DATABASE_URL
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class DatabaseService:
    """
    A unified data service wrapping database interactions for LangGraph agents.
    Replaces R2StorageService.
    """

    def __init__(self):
        self.db = SessionLocal()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.db.close()

    def close(self):
        self.db.close()

    def get_all_domains_last_updated(self) -> Dict[str, str]:
        """
        Scans all domains (from config tags) and returns the latest update dates from the DB.
        """
        latest_dates = {}
        for domain_slug in app_settings.tags.model_dump().keys():
            if domain_slug == "ainews":
                continue
            
            # Query the max date for the current domain
            result = self.db.query(func.max(Article.date)).filter(Article.domain == domain_slug).scalar()
            latest_dates[domain_slug] = result if result else "Never"
        return latest_dates

    def get_recent_history(self, domain: str, limit: int = 3) -> List[Dict[str, Any]]:
        """
        Fetches the N most recent articles for a specific domain to give prompting context.
        """
        articles = (
            self.db.query(Article)
            .filter(Article.domain == domain)
            .order_by(Article.date.desc(), Article.id.desc())
            .limit(limit)
            .all()
        )
        return [{
            "title": a.title,
            "topic": a.topic,
            "subtopics": a.subtopics
        } for a in articles]

    def save_article(
        self,
        domain: str,
        topic: str,
        subtopics: str,
        title: str,
        description: str,
        content: str,
        date: str,
        tags: List[str],
        read_time: str,
        slug: str
    ) -> bool:
        """
        Saves an article to the PostgreSQL database.
        Performs an upsert: updates the article if the slug already exists, otherwise inserts a new record.
        """
        try:
            # Check if an article with this slug already exists
            existing_article = self.db.query(Article).filter(Article.slug == slug).first()
            
            if existing_article:
                # Update existing article
                existing_article.domain = domain
                existing_article.topic = topic
                existing_article.subtopics = subtopics
                existing_article.title = title
                existing_article.description = description
                existing_article.content = content
                existing_article.date = date
                existing_article.tags = tags
                existing_article.read_time = read_time
                logger.info(f"[DB] Updating existing article with slug: {slug}")
            else:
                # Insert new article
                new_article = Article(
                    domain=domain,
                    topic=topic,
                    subtopics=subtopics,
                    title=title,
                    description=description,
                    content=content,
                    date=date,
                    tags=tags,
                    read_time=read_time,
                    slug=slug
                )
                self.db.add(new_article)
                logger.info(f"[DB] Saving new article to database: {slug}")
                
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            logger.error(f"[ERROR] Failed to save article to DB: {e}")
            return False
