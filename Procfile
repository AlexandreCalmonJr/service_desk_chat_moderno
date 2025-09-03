web: flask db upgrade && python -m spacy download pt_core_news_sm && gunicorn app:app --workers 2 --threads 2 --timeout 120 --preload
