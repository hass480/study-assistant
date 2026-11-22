from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

NOTES_PATH = Path(__file__).resolve().parent.parent / "data" / "notes.md"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

model = SentenceTransformer(EMBEDDING_MODEL)


def embed(text):
    return model.encode(text, normalize_embeddings=True)


def load_chunks(path=NOTES_PATH):
    text = Path(path).read_text()
    return [
        c.strip()
        for c in text.split("\n\n")
        if len(c.strip()) > 30 and not c.strip().startswith("#")
    ]


chunks = load_chunks()
vectors = embed(chunks)


def search(query, top_k=3):
    scores = vectors @ embed(query)
    best = np.argsort(scores)[::-1][:top_k]
    return [(float(scores[i]), chunks[i]) for i in best]
