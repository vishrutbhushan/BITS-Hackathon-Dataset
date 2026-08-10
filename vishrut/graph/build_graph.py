"""
Stage 2: batch-build the entity graph from extracted facts.

Run this ONCE over the whole corpus after Stage 0 (raw text extraction)
and Stage 1 (field extraction) are done -- not per-question. Produces a
populated sqlite DB matching db/schema.py that shapes/dispatcher.py
queries directly.

This module is intentionally driven by a plain Python list of extracted
records rather than reaching into the filesystem itself, so it's testable
without real documents (see tests/) and so Stage 1's extraction driver
(not written here -- it depends on your real doc_id -> doc_type -> text
mapping) can feed it however is convenient.
"""
from db.schema import get_connection, upsert_client, upsert_engineer


def build_graph(con, completion_certificates, reference_letters, personnel_certs, cvs):
    """
    Parameters are lists of dicts, one per source document, already run
    through extraction.field_extractors + parsers/*.py so values are
    canonical (int rupees, ISO dates, fixed-vocab grading/category).

    completion_certificates: [{project_name, client_name, engineer_name,
        value_rupees, completion_date, grading, role, category, doc_id}, ...]
    reference_letters: [{project_name, doc_id}, ...]
    personnel_certs: [{engineer_name, cert_type, cert_number, issue_date, doc_id}, ...]
    cvs: [{engineer_name, projects_led: [project_name, ...], doc_id}, ...]
    """
    import re

    def clean_proj(name):
        if not name:
            return ""
        name = name.lower()
        name = re.sub(r'project\s*name|name\s*of\s*work|work', '', name)
        name = re.sub(r'\s+', '', name)
        name = re.sub(r'[^a-z0-9]', '', name)
        return name

    referenced_projects = {r["project_name"] for r in reference_letters if r.get("project_name")}
    cleaned_referenced = {clean_proj(p) for p in referenced_projects}
    
    referenced_packages = set()
    for p in referenced_projects:
        pkg_match = re.search(r'\b[Pp][Kk][Gg]-(\d+)\b', p)
        if pkg_match:
            referenced_packages.add(int(pkg_match.group(1)))

    # engineer -> project links can come from either the certificate
    # itself (if it names the engineer) or the CV -- merge both sources.
    engineer_by_project = {}
    for cv in cvs:
        for p in cv.get("projects_led", []):
            engineer_by_project[p] = cv["engineer_name"]

    for cert in completion_certificates:
        if not cert.get("project_name") or not cert.get("client_name"):
            continue  # extraction gap -- log this in a real run, don't silently drop
        client_id = upsert_client(con, cert["client_name"])
        engineer_name = cert.get("engineer_name") or engineer_by_project.get(cert["project_name"])
        engineer_id = upsert_engineer(con, engineer_name) if engineer_name else None

        # Resolve whether this project has a reference letter
        has_ref = 0
        pkg_match = re.search(r'\b[Pp][Kk][Gg]-(\d+)\b', cert["project_name"])
        if pkg_match and int(pkg_match.group(1)) in referenced_packages:
            has_ref = 1
        elif clean_proj(cert["project_name"]) in cleaned_referenced:
            has_ref = 1

        con.execute(
            """INSERT INTO projects
               (name, client_id, engineer_id, category, value_rupees,
                completion_date, grading, role, has_reference_letter, source_doc_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cert["project_name"], client_id, engineer_id,
                cert.get("category", "other"), cert["value_rupees"],
                cert.get("completion_date"), cert.get("grading"), cert.get("role"),
                has_ref,
                cert.get("doc_id"),
            ),
        )

    for pc in personnel_certs:
        if not pc.get("engineer_name") or not pc.get("cert_type") or not pc.get("issue_date"):
            continue
        engineer_id = upsert_engineer(con, pc["engineer_name"])
        con.execute(
            """INSERT INTO engineer_certs
               (engineer_id, cert_type, cert_number, issue_date, source_doc_id)
               VALUES (?, ?, ?, ?, ?)""",
            (engineer_id, pc["cert_type"], pc.get("cert_number"), pc["issue_date"], pc.get("doc_id")),
        )

    con.commit()
    return con
