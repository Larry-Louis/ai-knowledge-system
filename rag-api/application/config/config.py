import os


class ApplicationConfig:
    INSIGHT_DUPLICATE_SIMILARITY_THRESHOLD = float(
        os.getenv("INSIGHT_DUPLICATE_SIMILARITY_THRESHOLD", "0.88")
    )
    INSIGHT_CONFLICT_SIMILARITY_THRESHOLD = float(
        os.getenv("INSIGHT_CONFLICT_SIMILARITY_THRESHOLD", "0.62")
    )


__all__ = ["ApplicationConfig"]