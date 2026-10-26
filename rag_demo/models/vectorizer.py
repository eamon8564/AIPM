"""轻量词面检索基线：字符 n-gram TF-IDF，并非语义 embedding。"""

from sklearn.feature_extraction.text import TfidfVectorizer


def create_vectorizer() -> TfidfVectorizer:
    """以连续 2～4 个字符为特征，适配无空格分词的中文文本。"""
    return TfidfVectorizer(analyzer="char", ngram_range=(2, 4), lowercase=True)
