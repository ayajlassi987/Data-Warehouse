
CREATE SCHEMA IF NOT EXISTS dw;

CREATE TABLE IF NOT EXISTS dw.dim_journal (
    journal_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    journal_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dw.dim_year (
    year_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS dw.dim_author (
    author_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    author_name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dw.dim_keyword (
    keyword_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    keyword TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dw.dim_mesh_term (
    mesh_term_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mesh_term TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dw.dim_publication_type (
    publication_type_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    publication_type TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS dw.fact_article (
    pmid TEXT PRIMARY KEY,
    title TEXT,
    abstract TEXT,
    doi TEXT,
    language TEXT,
    publication_date_text TEXT,
    journal_id BIGINT REFERENCES dw.dim_journal(journal_id),
    year_id INTEGER REFERENCES dw.dim_year(year_id),
    author_count INTEGER,
    keyword_count INTEGER,
    mesh_count INTEGER,
    abstract_words INTEGER
);

CREATE TABLE IF NOT EXISTS dw.bridge_article_author (
    pmid TEXT REFERENCES dw.fact_article(pmid),
    author_id BIGINT REFERENCES dw.dim_author(author_id),
    author_order INTEGER,
    PRIMARY KEY (pmid, author_id)
);

CREATE TABLE IF NOT EXISTS dw.bridge_article_keyword (
    pmid TEXT REFERENCES dw.fact_article(pmid),
    keyword_id BIGINT REFERENCES dw.dim_keyword(keyword_id),
    PRIMARY KEY (pmid, keyword_id)
);

CREATE TABLE IF NOT EXISTS dw.bridge_article_mesh (
    pmid TEXT REFERENCES dw.fact_article(pmid),
    mesh_term_id BIGINT REFERENCES dw.dim_mesh_term(mesh_term_id),
    PRIMARY KEY (pmid, mesh_term_id)
);

CREATE TABLE IF NOT EXISTS dw.bridge_article_publication_type (
    pmid TEXT REFERENCES dw.fact_article(pmid),
    publication_type_id BIGINT
        REFERENCES dw.dim_publication_type(publication_type_id),
    PRIMARY KEY (pmid, publication_type_id)
);

CREATE INDEX IF NOT EXISTS idx_fact_article_year
    ON dw.fact_article(year_id);

CREATE INDEX IF NOT EXISTS idx_fact_article_journal
    ON dw.fact_article(journal_id);

CREATE INDEX IF NOT EXISTS idx_article_author_author
    ON dw.bridge_article_author(author_id);

CREATE INDEX IF NOT EXISTS idx_article_keyword_keyword
    ON dw.bridge_article_keyword(keyword_id);

CREATE INDEX IF NOT EXISTS idx_article_mesh_term
    ON dw.bridge_article_mesh(mesh_term_id);
