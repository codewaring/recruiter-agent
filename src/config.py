import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    source_api_base_url: str = os.getenv("SOURCE_API_BASE_URL", "http://127.0.0.1:8080")
    fallback_jd_index_bucket: str = os.getenv("FALLBACK_JD_INDEX_BUCKET", "jackytest007")
    fallback_jd_index_object: str = os.getenv("FALLBACK_JD_INDEX_OBJECT", "generated-jds/.index.json")
    model_name: str = os.getenv("MODEL_NAME", "gemini-2.5-pro")
    google_cloud_project: str = os.getenv("GOOGLE_CLOUD_PROJECT", "")
    google_cloud_location: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    google_genai_use_vertexai: str = os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "true")


settings = Settings()
