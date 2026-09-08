"""Create the shared PostgreSQL history table once, from an administrator PC."""
from backend.app.repositories.history_repository import history_repository

if __name__ == "__main__":
    history_repository.initialize_schema()
    print("PostgreSQL schema initialized: ky_analysis_history")
