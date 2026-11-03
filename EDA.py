"""Exploratory Data Analysis (EDA) for a folder of PubMed XML files.

Usage:
    python pubmed_eda.py --input "data/pubmed doc" --output "eda_output"

The input folder should contain extracted .xml files. Handles files containing
PubmedArticle and/or PubmedBookArticle records, including nested XML text.
"""
from pathlib import Path
import argparse
import re
import sys
import pandas as pd
import matplotlib.pyplot as plt
from lxml import etree


def local_children(node, name):
    """Direct children with a given local tag name (works with XML namespaces)."""
    if node is None:
        return []
    return [child for child in node if isinstance(child.tag, str) and etree.QName(child).localname == name]


def child(node, name):
    items = local_children(node, name)
    return items[0] if items else None


def text_content(node):
    """Collect text, including text inside inline XML tags."""
    if node is None:
        return None
    value = " ".join("".join(node.itertext()).split())
    return value or None


def get_text(node, *path):
    """Get text following a path of direct child tag names."""
    cur = node
    for name in path:
        cur = child(cur, name)
        if cur is None:
            return None
    return text_content(cur)


def get_all_text(node, name):
    return [text_content(x) for x in local_children(node, name) if text_content(x)]


def extract_article(article_node, source_file):
    # PubMed journal article hierarchy: PubmedArticle > MedlineCitation > Article
    citation = child(article_node, "MedlineCitation") or child(article_node, "BookDocument")
    if citation is None:
        citation = article_node
    article = child(citation, "Article") or citation
    journal = child(article, "Journal")
    journal_issue = child(journal, "JournalIssue")
    pubdate = child(journal_issue, "PubDate")
    if pubdate is None:
        pubdate = child(article, "ArticleDate")
    if pubdate is None:
        pubdate = child(article, "DateCreated")

    # PubMed usually gives Year; MedlineDate may contain a range or descriptive date.
    year_text = get_text(pubdate, "Year") if pubdate is not None else None
    if not year_text and pubdate is not None:
        year_text = get_text(pubdate, "MedlineDate")
    if not year_text:
        year_text = get_text(citation, "DateCreated", "Year")
    year_match = re.search(r"\b(18|19|20|21)\d{2}\b", year_text or "")
    year = int(year_match.group(0)) if year_match else None

    pmid = get_text(citation, "PMID")
    if not pmid:
        pmid = get_text(article_node, "PMID")

    title = get_text(article, "ArticleTitle") or get_text(article, "BookTitle")
    abstract_node = child(article, "Abstract")
    abstract_parts = []
    if abstract_node is not None:
        for part in local_children(abstract_node, "AbstractText"):
            value = text_content(part)
            label = part.get("Label") or part.get("NlmCategory")
            if value:
                abstract_parts.append(f"{label}: {value}" if label else value)
    abstract = " ".join(abstract_parts) or None

    authors = []
    author_list = child(article, "AuthorList")
    for author in local_children(author_list, "Author") if author_list is not None else []:
        collective = get_text(author, "CollectiveName")
        last = get_text(author, "LastName")
        fore = get_text(author, "ForeName") or get_text(author, "Initials")
        name = collective or " ".join(x for x in [fore, last] if x)
        if name:
            authors.append(name)

    keywords = []
    for keyword_list in local_children(citation, "KeywordList"):
        keywords.extend(get_all_text(keyword_list, "Keyword"))
    # Some records place keyword lists elsewhere.
    if not keywords:
        for keyword_list in article_node.iter():
            if isinstance(keyword_list.tag, str) and etree.QName(keyword_list).localname == "KeywordList":
                keywords.extend(get_all_text(keyword_list, "Keyword"))

    mesh_terms = []
    mesh_list = child(citation, "MeshHeadingList")
    if mesh_list is not None:
        for heading in local_children(mesh_list, "MeshHeading"):
            descriptor = get_text(heading, "DescriptorName")
            qualifiers = get_all_text(child(heading, "QualifierName"), "QualifierName")
            # QualifierName elements are children of MeshHeading, not nested in one another.
            qualifiers = [text_content(q) for q in local_children(heading, "QualifierName") if text_content(q)]
            if descriptor:
                mesh_terms.append(descriptor + (" — " + ", ".join(qualifiers) if qualifiers else ""))

    publication_types = []
    ptl = child(article, "PublicationTypeList")
    if ptl is not None:
        publication_types = get_all_text(ptl, "PublicationType")

    article_ids = child(child(article_node, "PubmedData"), "ArticleIdList")
    doi = None
    if article_ids is not None:
        for aid in local_children(article_ids, "ArticleId"):
            if (aid.get("IdType") or "").lower() == "doi":
                doi = text_content(aid)
                break

    language_values = get_all_text(article, "Language")
    return {
        "pmid": str(pmid).strip() if pmid else None,
        "title": title,
        "abstract": abstract,
        "journal": get_text(journal, "Title") if journal is not None else None,
        "year": year,
        "publication_date_text": year_text,
        "language": "; ".join(language_values) if language_values else None,
        "doi": doi,
        "authors": authors,
        "author_count": len(authors),
        "keywords": keywords,
        "keyword_count": len(keywords),
        "mesh_terms": mesh_terms,
        "mesh_count": len(mesh_terms),
        "publication_types": publication_types,
        "source_file": str(source_file),
        "title_chars": len(title) if title else 0,
        "abstract_chars": len(abstract) if abstract else 0,
        "abstract_words": len(abstract.split()) if abstract else 0,
    }


def parse_xml_file(path):
    parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=False, huge_tree=True)
    tree = etree.parse(str(path), parser)
    root = tree.getroot()
    records = []
    # Find article records anywhere in each file, namespace-independently.
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        tag = etree.QName(node).localname
        if tag in {"PubmedArticle", "PubmedBookArticle"}:
            records.append(extract_article(node, path))
    # Some XML samples may be a single article-shaped root.
    if not records and etree.QName(root).localname in {"PubmedArticle", "PubmedBookArticle"}:
        records.append(extract_article(root, path))
    return records


def save_bar(series, title, xlabel, path, top_n=20, horizontal=True):
    series = series.dropna().astype(str)
    counts = series.value_counts().head(top_n)
    if counts.empty:
        return
    plt.figure(figsize=(10, max(4, min(9, len(counts) * 0.32))))
    if horizontal:
        counts.sort_values().plot(kind="barh")
        plt.xlabel("Number of articles")
        plt.ylabel(xlabel)
    else:
        counts.plot(kind="bar")
        plt.ylabel("Number of articles")
        plt.xlabel(xlabel)
        plt.xticks(rotation=45, ha="right")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(path, dpi=150)
    plt.close()


def main():
    ap = argparse.ArgumentParser(description="EDA for PubMed XML files")
    ap.add_argument("--input", required=True, help="Folder containing extracted XML files")
    ap.add_argument("--output", default="eda_output", help="Directory for CSV reports and charts")
    args = ap.parse_args()

    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not input_dir.exists():
        sys.exit(f"Input folder not found: {input_dir}")

    xml_files = sorted(input_dir.rglob("*.xml"))
    if not xml_files:
        sys.exit(f"No .xml files found in: {input_dir}. Extract the RAR archive first.")

    all_records, errors = [], []
    for idx, xml_file in enumerate(xml_files, 1):
        try:
            recs = parse_xml_file(xml_file)
            if not recs:
                errors.append({"file": str(xml_file), "error": "No PubmedArticle/PubmedBookArticle record found"})
            all_records.extend(recs)
        except Exception as exc:
            errors.append({"file": str(xml_file), "error": f"{type(exc).__name__}: {exc}"})
        if idx % 250 == 0 or idx == len(xml_files):
            print(f"Processed {idx}/{len(xml_files)} XML files; articles extracted: {len(all_records)}")

    if not all_records:
        sys.exit("No articles extracted. Inspect the XML structure and error report.")

    df = pd.DataFrame(all_records)
    # Store lists as readable strings in the flat article table.
    for col in ["authors", "keywords", "mesh_terms", "publication_types"]:
        df[col] = df[col].apply(lambda x: " | ".join(x) if isinstance(x, list) else x)
    df.to_csv(output_dir / "articles_eda.csv", index=False, encoding="utf-8-sig")
    if errors:
        pd.DataFrame(errors).to_csv(output_dir / "xml_errors.csv", index=False, encoding="utf-8-sig")

    # Basic profile
    summary = {
        "xml_files_found": len(xml_files),
        "articles_extracted": len(df),
        "unique_non_null_pmids": df["pmid"].dropna().nunique(),
        "duplicate_pmid_rows": int(df["pmid"].notna().sum() - df.loc[df["pmid"].notna(), "pmid"].nunique()),
        "rows_without_pmid": int(df["pmid"].isna().sum()),
        "rows_without_title": int(df["title"].isna().sum()),
        "rows_without_abstract": int(df["abstract"].isna().sum()),
        "rows_without_journal": int(df["journal"].isna().sum()),
        "rows_without_year": int(df["year"].isna().sum()),
        "rows_without_doi": int(df["doi"].isna().sum()),
        "xml_files_with_errors_or_no_records": len(errors),
        "year_min": int(df["year"].min()) if df["year"].notna().any() else None,
        "year_max": int(df["year"].max()) if df["year"].notna().any() else None,
        "mean_abstract_words": round(float(df["abstract_words"].mean()), 2),
        "median_abstract_words": round(float(df["abstract_words"].median()), 2),
    }
    pd.DataFrame([{"metric": k, "value": v} for k, v in summary.items()]).to_csv(
        output_dir / "summary.csv", index=False, encoding="utf-8-sig"
    )

    # Missingness table
    missing = pd.DataFrame({
        "column": df.columns,
        "missing_count": [int(df[c].isna().sum()) for c in df.columns],
    })
    missing["missing_pct"] = (missing["missing_count"] / len(df) * 100).round(2)
    missing.sort_values("missing_pct", ascending=False).to_csv(
        output_dir / "missing_values.csv", index=False, encoding="utf-8-sig"
    )

    # Relational/exploded outputs useful for later warehouse modelling.
    author_rows, keyword_rows, mesh_rows, type_rows = [], [], [], []
    for rec in all_records:
        for author_order, author in enumerate(rec["authors"], 1):
            author_rows.append({"pmid": rec["pmid"], "author_order": author_order, "author": author})
        for keyword in rec["keywords"]:
            keyword_rows.append({"pmid": rec["pmid"], "keyword": keyword})
        for term in rec["mesh_terms"]:
            mesh_rows.append({"pmid": rec["pmid"], "mesh_term": term})
        for pub_type in rec["publication_types"]:
            type_rows.append({"pmid": rec["pmid"], "publication_type": pub_type})
    for name, rows in [("article_authors.csv", author_rows), ("article_keywords.csv", keyword_rows),
                       ("article_mesh_terms.csv", mesh_rows), ("article_publication_types.csv", type_rows)]:
        pd.DataFrame(rows, columns=(rows[0].keys() if rows else ["pmid"])).to_csv(
            output_dir / name, index=False, encoding="utf-8-sig"
        )

    # Charts
    year_counts = df.dropna(subset=["year"]).groupby("year").size().sort_index()
    if not year_counts.empty:
        plt.figure(figsize=(11, 5))
        year_counts.plot(kind="line", marker="o", markersize=3)
        plt.title("PubMed articles by publication year")
        plt.xlabel("Publication year")
        plt.ylabel("Number of articles")
        plt.grid(True, alpha=0.25)
        plt.tight_layout()
        plt.savefig(output_dir / "articles_by_year.png", dpi=150)
        plt.close()

    save_bar(df["journal"], "Top journals in the dataset", "Journal", output_dir / "top_journals.png")
    save_bar(df["language"], "Articles by language", "Language", output_dir / "languages.png")
    save_bar(df["abstract_words"].astype(str), "Abstract word-count frequency (top values)", "Abstract word count", output_dir / "abstract_word_counts.png")

    # Normalize multi-value fields for meaningful frequency analysis.
    for column, output_name, chart_name, label in [
        ("keywords", "top_keywords.csv", "top_keywords.png", "Keyword"),
        ("mesh_terms", "top_mesh_terms.csv", "top_mesh_terms.png", "MeSH term"),
        ("publication_types", "top_publication_types.csv", "top_publication_types.png", "Publication type"),
    ]:
        vals = []
        for rec in all_records:
            vals.extend(rec[column])
        freq = pd.Series(vals, dtype="string").value_counts().rename_axis(label).reset_index(name="article_term_count")
        freq.to_csv(output_dir / output_name, index=False, encoding="utf-8-sig")
        if not freq.empty:
            save_bar(pd.Series(vals), f"Top {label.lower()}s", label, output_dir / chart_name)

    # Duplicate identifiers for manual review
    duplicates = df[df["pmid"].notna() & df["pmid"].duplicated(keep=False)].sort_values("pmid")
    duplicates.to_csv(output_dir / "duplicate_pmids.csv", index=False, encoding="utf-8-sig")

    print("\n=== EDA SUMMARY ===")
    for key, value in summary.items():
        print(f"{key}: {value}")
    print(f"\nOutputs saved to: {output_dir.resolve()}")
    print("Main files: articles_eda.csv, summary.csv, missing_values.csv, top_keywords.csv, top_mesh_terms.csv, and PNG charts.")

if __name__ == "__main__":
    main()
