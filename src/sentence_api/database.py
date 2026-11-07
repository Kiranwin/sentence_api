import time
from contextlib import contextmanager
from typing import List, Dict, Optional

from sentence_api.config import get_db_config

_config: dict | None = None


def _init() -> None:
    global _config
    if _config is None:
        _config = get_db_config()
        backend = _config.get("type", "sqlite")
        if backend != "sqlite":
            raise ValueError(f"不支持的数据库类型: {backend}")


def _sql(template: str) -> str:
    """将 {ph} 替换为 SQLite 占位符。"""
    return template.replace("{ph}", "?")


@contextmanager
def get_db():
    _init()
    import sqlite3

    path = _config.get("sqlite", {}).get("path", "sentences.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _execute(conn, sql_template: str, params=None):
    """执行参数化 SQL，返回光标对象。"""
    sql = _sql(sql_template)
    if params is not None:
        return conn.execute(sql, params)
    return conn.execute(sql)


def _insert(conn, sql_template: str, params: tuple) -> int:
    """执行 INSERT 并返回新行的 id。"""
    cur = conn.execute(_sql(sql_template), params)
    return cur.lastrowid


def init_db():
    _init()
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS sentences (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hitokoto TEXT NOT NULL,
                author TEXT NOT NULL,
                commit_from TEXT,
                created_at INTEGER NOT NULL,
                length INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sentence_categories (
                sentence_id INTEGER,
                category_id INTEGER,
                FOREIGN KEY (sentence_id) REFERENCES sentences(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE,
                PRIMARY KEY (sentence_id, category_id)
            );
            CREATE INDEX IF NOT EXISTS idx_sentence_category ON sentence_categories(category_id);
        """)
        conn.execute(
            "INSERT OR IGNORE INTO categories (name) VALUES (?)",
            ("默认分类",),
        )
        conn.commit()


def _current_timestamp() -> int:
    return int(time.time())


# ---------- 分类操作 ----------
def get_or_create_category(conn, name: str) -> int:
    cur = _execute(
        conn,
        "SELECT id FROM categories WHERE name = {ph}",
        (name.strip(),),
    )
    row = cur.fetchone()
    if row:
        return row["id"]
    return _insert(
        conn,
        "INSERT INTO categories (name) VALUES ({ph})",
        (name.strip(),),
    )


def get_all_categories(conn) -> List[str]:
    cur = _execute(conn, "SELECT name FROM categories ORDER BY name")
    return [row["name"] for row in cur.fetchall()]


def delete_category(conn, name: str) -> bool:
    cur = _execute(
        conn,
        "DELETE FROM categories WHERE name = {ph}",
        (name,),
    )
    return cur.rowcount > 0


# ---------- 句子 CRUD ----------
def add_sentence(
    conn, hitokoto: str, author: str, categories: List[str], commit_from: str = "web"
) -> int:
    if not hitokoto.strip():
        raise ValueError("句子内容不能为空")
    if not author or not author.strip():
        author = "默认作者"
    now = _current_timestamp()
    length = len(hitokoto)

    sentence_id = _insert(
        conn,
        "INSERT INTO sentences (hitokoto, author, commit_from, created_at, length) "
        "VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
        (hitokoto.strip(), author.strip(), commit_from.strip(), now, length),
    )

    if not categories:
        default_id = get_or_create_category(conn, "默认分类")
        _execute(
            conn,
            "INSERT INTO sentence_categories (sentence_id, category_id) VALUES ({ph}, {ph})",
            (sentence_id, default_id),
        )
    else:
        for cat_name in categories:
            if cat_name and cat_name.strip():
                cat_id = get_or_create_category(conn, cat_name.strip())
                _execute(
                    conn,
                    "INSERT INTO sentence_categories (sentence_id, category_id) VALUES ({ph}, {ph})",
                    (sentence_id, cat_id),
                )
    return sentence_id


def update_sentence(
    conn, sid: int, hitokoto: str, author: str, categories: List[str], commit_from: str
) -> bool:
    if not hitokoto.strip():
        raise ValueError("句子内容不能为空")
    if not author or not author.strip():
        author = "默认作者"
    cur = _execute(
        conn,
        "UPDATE sentences SET hitokoto={ph}, author={ph}, commit_from={ph}, length={ph} "
        "WHERE id={ph}",
        (hitokoto.strip(), author.strip(), commit_from.strip(), len(hitokoto), sid),
    )
    if cur.rowcount == 0:
        return False
    _execute(
        conn,
        "DELETE FROM sentence_categories WHERE sentence_id = {ph}",
        (sid,),
    )
    if not categories:
        default_id = get_or_create_category(conn, "默认分类")
        _execute(
            conn,
            "INSERT INTO sentence_categories (sentence_id, category_id) VALUES ({ph}, {ph})",
            (sid, default_id),
        )
    else:
        for cat_name in categories:
            if cat_name and cat_name.strip():
                cat_id = get_or_create_category(conn, cat_name.strip())
                _execute(
                    conn,
                    "INSERT INTO sentence_categories (sentence_id, category_id) VALUES ({ph}, {ph})",
                    (sid, cat_id),
                )
    return True


def delete_sentence(conn, sid: int) -> bool:
    cur = _execute(conn, "DELETE FROM sentences WHERE id={ph}", (sid,))
    return cur.rowcount > 0


def get_sentence_by_id(conn, sid: int) -> Optional[Dict]:
    cur = _execute(
        conn,
        "SELECT id, hitokoto, author, commit_from, created_at, length "
        "FROM sentences WHERE id={ph}",
        (sid,),
    )
    row = cur.fetchone()
    if not row:
        return None
    sentence = dict(row)
    cur_cat = _execute(
        conn,
        "SELECT c.name FROM categories c "
        "JOIN sentence_categories sc ON c.id = sc.category_id "
        "WHERE sc.sentence_id = {ph}",
        (sid,),
    )
    sentence["categories"] = [r["name"] for r in cur_cat.fetchall()]
    return sentence


def list_sentences(conn, page: int = 1, limit: int = 20) -> tuple:
    offset = (page - 1) * limit
    cur = _execute(
        conn,
        "SELECT id, hitokoto, author, commit_from, created_at, length "
        "FROM sentences ORDER BY id DESC LIMIT {ph} OFFSET {ph}",
        (limit, offset),
    )
    items = []
    for row in cur.fetchall():
        s = dict(row)
        cur_cat = _execute(
            conn,
            "SELECT c.name FROM categories c "
            "JOIN sentence_categories sc ON c.id = sc.category_id "
            "WHERE sc.sentence_id = {ph}",
            (s["id"],),
        )
        s["categories"] = [r["name"] for r in cur_cat.fetchall()]
        items.append(s)
    total = _execute(conn, "SELECT COUNT(*) as cnt FROM sentences").fetchone()["cnt"]
    return items, total


def random_sentence(conn, category: str = None) -> Optional[Dict]:
    if category:
        cur = _execute(
            conn,
            "SELECT s.id, s.hitokoto, s.author, s.commit_from, s.created_at, s.length "
            "FROM sentences s "
            "JOIN sentence_categories sc ON s.id = sc.sentence_id "
            "JOIN categories c ON sc.category_id = c.id "
            "WHERE c.name = {ph} "
            "ORDER BY RANDOM() LIMIT 1",
            (category.strip(),),
        )
    else:
        cur = _execute(
            conn,
            "SELECT id, hitokoto, author, commit_from, created_at, length "
            "FROM sentences ORDER BY RANDOM() LIMIT 1",
        )
    row = cur.fetchone()
    if not row:
        return None
    sentence = dict(row)
    cur_cat = _execute(
        conn,
        "SELECT c.name FROM categories c "
        "JOIN sentence_categories sc ON c.id = sc.category_id "
        "WHERE sc.sentence_id = {ph}",
        (sentence["id"],),
    )
    sentence["categories"] = [r["name"] for r in cur_cat.fetchall()]
    return sentence


# ---------- 导入导出 ----------
def import_sentences(conn, sentences_list: List[dict], replace: bool = False) -> int:
    if replace:
        _execute(conn, "DELETE FROM sentences")
    count = 0
    for item in sentences_list:
        try:
            hitokoto = item.get("hitokoto", "").strip()
            if not hitokoto:
                continue
            author = item.get("author", "").strip()
            if not author:
                author = "默认作者"
            commit_from = item.get("commit_from", "import")
            created_at = item.get("created_at", _current_timestamp())
            length = item.get("length", len(hitokoto))
            categories = item.get("categories", [])
            if not categories and "type" in item:
                categories = [item["type"]]

            sid = _insert(
                conn,
                "INSERT INTO sentences (hitokoto, author, commit_from, created_at, length) "
                "VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                (hitokoto, author, commit_from, created_at, length),
            )

            if not categories:
                default_id = get_or_create_category(conn, "默认分类")
                _execute(
                    conn,
                    "INSERT INTO sentence_categories (sentence_id, category_id) "
                    "VALUES ({ph}, {ph})",
                    (sid, default_id),
                )
            else:
                for cat_name in categories:
                    if cat_name and cat_name.strip():
                        cat_id = get_or_create_category(conn, cat_name.strip())
                        _execute(
                            conn,
                            "INSERT INTO sentence_categories (sentence_id, category_id) "
                            "VALUES ({ph}, {ph})",
                            (sid, cat_id),
                        )
            count += 1
        except Exception as e:
            print(f"导入失败: {e}")
            continue
    return count


def export_all_sentences(conn) -> List[Dict]:
    cur = _execute(
        conn,
        "SELECT id, hitokoto, author, commit_from, created_at, length "
        "FROM sentences ORDER BY id",
    )
    sentences = []
    for row in cur.fetchall():
        s = dict(row)
        cur_cat = _execute(
            conn,
            "SELECT c.name FROM categories c "
            "JOIN sentence_categories sc ON c.id = sc.category_id "
            "WHERE sc.sentence_id = {ph}",
            (s["id"],),
        )
        s["categories"] = [r["name"] for r in cur_cat.fetchall()]
        sentences.append(s)
    return sentences
