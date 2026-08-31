"""Build the single owner-facing GODFIN private-launch completion runbook."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "docs" / "GODFIN_OWNER_COMPLETION_RUNBOOK.docx"

NAVY = "163A5F"
BLUE = "2E74B5"
DARK_BLUE = "1F4D78"
INK = "172033"
MUTED = "667085"
LIGHT_BLUE = "E8EEF5"
LIGHT_GRAY = "F2F4F7"
GREEN_FILL = "EAF7EF"
GREEN = "17663A"
AMBER_FILL = "FFF4D8"
AMBER = "7A5A00"
RED_FILL = "FDECEC"
RED = "9B1C1C"
WHITE = "FFFFFF"
TABLE_WIDTH_DXA = 9360
TABLE_INDENT_DXA = 120


def set_run_font(
    run,
    *,
    name: str = "Calibri",
    size: float | None = None,
    color: str | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
) -> None:
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    if size is not None:
        run.font.size = Pt(size)
    if color is not None:
        run.font.color.rgb = RGBColor.from_string(color)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def set_cell_shading(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd"))
    if shd is None:
        shd = OxmlElement("w:shd")
        tc_pr.append(shd)
    shd.set(qn("w:fill"), fill)


def set_cell_margins(
    cell,
    *,
    top: int = 80,
    start: int = 120,
    bottom: int = 80,
    end: int = 120,
) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    tc_mar = tc_pr.first_child_found_in("w:tcMar")
    if tc_mar is None:
        tc_mar = OxmlElement("w:tcMar")
        tc_pr.append(tc_mar)
    for margin, value in (
        ("top", top),
        ("start", start),
        ("bottom", bottom),
        ("end", end),
    ):
        node = tc_mar.find(qn(f"w:{margin}"))
        if node is None:
            node = OxmlElement(f"w:{margin}")
            tc_mar.append(node)
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")


def set_table_geometry(table, widths: list[int]) -> None:
    if sum(widths) != TABLE_WIDTH_DXA:
        raise ValueError(f"Table widths must total {TABLE_WIDTH_DXA}: {widths}")
    table.autofit = False
    tbl_pr = table._tbl.tblPr
    tbl_w = tbl_pr.first_child_found_in("w:tblW")
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(TABLE_WIDTH_DXA))
    tbl_w.set(qn("w:type"), "dxa")
    tbl_ind = tbl_pr.first_child_found_in("w:tblInd")
    if tbl_ind is None:
        tbl_ind = OxmlElement("w:tblInd")
        tbl_pr.append(tbl_ind)
    tbl_ind.set(qn("w:w"), str(TABLE_INDENT_DXA))
    tbl_ind.set(qn("w:type"), "dxa")

    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(width))
        grid.append(col)

    for row in table.rows:
        for index, cell in enumerate(row.cells):
            tc_pr = cell._tc.get_or_add_tcPr()
            tc_w = tc_pr.first_child_found_in("w:tcW")
            if tc_w is None:
                tc_w = OxmlElement("w:tcW")
                tc_pr.append(tc_w)
            tc_w.set(qn("w:w"), str(widths[index]))
            tc_w.set(qn("w:type"), "dxa")
            set_cell_margins(cell)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def mark_header_row(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    tbl_header = OxmlElement("w:tblHeader")
    tbl_header.set(qn("w:val"), "true")
    tr_pr.append(tbl_header)


def prevent_row_split(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:cantSplit")) is None:
        tr_pr.append(OxmlElement("w:cantSplit"))


def add_field(paragraph, instruction: str) -> None:
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    value = OxmlElement("w:t")
    value.text = "1"
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run = paragraph.add_run()
    run._r.extend([begin, instr, separate, value, end])
    set_run_font(run, size=9, color=MUTED)


def add_hyperlink(paragraph, text: str, url: str) -> None:
    relationship_id = paragraph.part.relate_to(
        url,
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink",
        is_external=True,
    )
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), relationship_id)
    run = OxmlElement("w:r")
    run_props = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), BLUE)
    underline = OxmlElement("w:u")
    underline.set(qn("w:val"), "single")
    run_props.extend([color, underline])
    text_element = OxmlElement("w:t")
    text_element.text = text
    run.extend([run_props, text_element])
    hyperlink.append(run)
    paragraph._p.append(hyperlink)


def configure_styles(document: Document) -> None:
    styles = document.styles
    normal = styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor.from_string(INK)
    normal._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    normal._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after = Pt(4)
    normal.paragraph_format.line_spacing = 1.15

    for style_name, size, color, before, after in (
        ("Heading 1", 16, BLUE, 18, 10),
        ("Heading 2", 13, BLUE, 14, 7),
        ("Heading 3", 12, DARK_BLUE, 10, 5),
    ):
        style = styles[style_name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.bold = True
        style.font.color.rgb = RGBColor.from_string(color)
        style._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
        style._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
        style.paragraph_format.space_before = Pt(before)
        style.paragraph_format.space_after = Pt(after)
        style.paragraph_format.keep_with_next = True

    if "Runbook Caption" not in styles:
        caption = styles.add_style("Runbook Caption", WD_STYLE_TYPE.PARAGRAPH)
    else:
        caption = styles["Runbook Caption"]
    caption.font.name = "Calibri"
    caption.font.size = Pt(9)
    caption.font.color.rgb = RGBColor.from_string(MUTED)
    caption._element.rPr.rFonts.set(qn("w:ascii"), "Calibri")
    caption._element.rPr.rFonts.set(qn("w:hAnsi"), "Calibri")
    caption.paragraph_format.space_before = Pt(4)
    caption.paragraph_format.space_after = Pt(4)
    caption.paragraph_format.line_spacing = 1.15


def add_numbering(document: Document, *, kind: str) -> int:
    numbering = document.part.numbering_part.element
    abstract_ids = [
        int(node.get(qn("w:abstractNumId")))
        for node in numbering.findall(qn("w:abstractNum"))
    ]
    num_ids = [int(node.get(qn("w:numId"))) for node in numbering.findall(qn("w:num"))]
    abstract_id = max(abstract_ids, default=0) + 1
    num_id = max(num_ids, default=0) + 1

    abstract = OxmlElement("w:abstractNum")
    abstract.set(qn("w:abstractNumId"), str(abstract_id))
    multi = OxmlElement("w:multiLevelType")
    multi.set(qn("w:val"), "singleLevel")
    abstract.append(multi)
    level = OxmlElement("w:lvl")
    level.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:start")
    start.set(qn("w:val"), "1")
    level.append(start)
    num_fmt = OxmlElement("w:numFmt")
    num_fmt.set(qn("w:val"), "decimal" if kind == "decimal" else "bullet")
    level.append(num_fmt)
    level_text = OxmlElement("w:lvlText")
    level_text.set(
        qn("w:val"),
        "%1." if kind == "decimal" else ("☐" if kind == "check" else "•"),
    )
    level.append(level_text)
    if kind == "decimal":
        # A space suffix is stable when LibreOffice paginates a long list; the
        # default tab suffix can strand the next marker at the prior line end.
        suffix = OxmlElement("w:suff")
        suffix.set(qn("w:val"), "space")
        level.append(suffix)
    justification = OxmlElement("w:lvlJc")
    justification.set(qn("w:val"), "left")
    level.append(justification)
    p_pr = OxmlElement("w:pPr")
    # Decimal instructions exceed 100 items, so reserve enough marker width for
    # three digits plus punctuation. Bullet/check lists retain the compact inset.
    list_left = "900" if kind == "decimal" else "720"
    list_hanging = "540" if kind == "decimal" else "360"
    tabs = OxmlElement("w:tabs")
    tab = OxmlElement("w:tab")
    tab.set(qn("w:val"), "num")
    tab.set(qn("w:pos"), list_left)
    tabs.append(tab)
    indent = OxmlElement("w:ind")
    indent.set(qn("w:left"), list_left)
    indent.set(qn("w:hanging"), list_hanging)
    spacing = OxmlElement("w:spacing")
    spacing.set(qn("w:after"), "60")
    spacing.set(qn("w:line"), "276")
    spacing.set(qn("w:lineRule"), "auto")
    p_pr.extend([tabs, indent, spacing])
    level.append(p_pr)
    if kind in {"bullet", "check"}:
        r_pr = OxmlElement("w:rPr")
        fonts = OxmlElement("w:rFonts")
        fonts.set(qn("w:ascii"), "Segoe UI Symbol")
        fonts.set(qn("w:hAnsi"), "Segoe UI Symbol")
        r_pr.append(fonts)
        level.append(r_pr)
    abstract.append(level)
    numbering.append(abstract)

    num = OxmlElement("w:num")
    num.set(qn("w:numId"), str(num_id))
    abstract_ref = OxmlElement("w:abstractNumId")
    abstract_ref.set(qn("w:val"), str(abstract_id))
    num.append(abstract_ref)
    numbering.append(num)
    return num_id


def add_list_item(document: Document, text: str, num_id: int, *, bold_prefix: str | None = None):
    paragraph = document.add_paragraph()
    p_pr = paragraph._p.get_or_add_pPr()
    num_pr = OxmlElement("w:numPr")
    level = OxmlElement("w:ilvl")
    level.set(qn("w:val"), "0")
    number = OxmlElement("w:numId")
    number.set(qn("w:val"), str(num_id))
    num_pr.extend([level, number])
    p_pr.append(num_pr)
    paragraph.paragraph_format.keep_together = True
    if bold_prefix and text.startswith(bold_prefix):
        prefix = paragraph.add_run(bold_prefix)
        prefix.bold = True
        paragraph.add_run(text[len(bold_prefix) :])
    else:
        paragraph.add_run(text)
    return paragraph


def add_callout(
    document: Document,
    label: str,
    body: str,
    *,
    tone: str = "info",
) -> None:
    fill, color = {
        "good": (GREEN_FILL, GREEN),
        "warn": (AMBER_FILL, AMBER),
        "risk": (RED_FILL, RED),
        "info": (LIGHT_BLUE, NAVY),
    }[tone]
    paragraph = document.add_paragraph()
    paragraph.paragraph_format.left_indent = Inches(0.08)
    paragraph.paragraph_format.right_indent = Inches(0.08)
    paragraph.paragraph_format.space_before = Pt(5)
    paragraph.paragraph_format.space_after = Pt(8)
    paragraph.paragraph_format.line_spacing = 1.2
    paragraph.paragraph_format.keep_together = True
    p_pr = paragraph._p.get_or_add_pPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill)
    borders = OxmlElement("w:pBdr")
    left_border = OxmlElement("w:left")
    left_border.set(qn("w:val"), "single")
    left_border.set(qn("w:sz"), "18")
    left_border.set(qn("w:space"), "8")
    left_border.set(qn("w:color"), color)
    borders.append(left_border)
    p_pr.extend([shading, borders])
    lead = paragraph.add_run(f"{label}  ")
    set_run_font(lead, size=10.5, color=color, bold=True)
    content = paragraph.add_run(body)
    set_run_font(content, size=10.5, color=INK)


def add_table(
    document: Document,
    headers: list[str],
    rows: list[list[str]],
    widths: list[int],
) -> None:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    header = table.rows[0]
    for index, text in enumerate(headers):
        cell = header.cells[index]
        set_cell_shading(cell, LIGHT_BLUE)
        paragraph = cell.paragraphs[0]
        paragraph.paragraph_format.space_after = Pt(0)
        run = paragraph.add_run(text)
        set_run_font(run, size=9.5, color=NAVY, bold=True)
    mark_header_row(header)
    for row_values in rows:
        row = table.add_row()
        prevent_row_split(row)
        for index, text in enumerate(row_values):
            paragraph = row.cells[index].paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(0)
            run = paragraph.add_run(text)
            set_run_font(run, size=9.25, color=INK)
    set_table_geometry(table, widths)
    document.add_paragraph().paragraph_format.space_after = Pt(1)


def add_owner_fields(document: Document, fields: list[str]) -> None:
    for field in fields:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(4)
        label = paragraph.add_run(f"{field}: ")
        label.bold = True
        paragraph.add_run("_" * 74)


def add_source(document: Document, label: str, url: str) -> None:
    paragraph = document.add_paragraph(style="Runbook Caption")
    paragraph.add_run("Official reference: ")
    add_hyperlink(paragraph, label, url)


def build_document() -> Document:
    document = Document()
    section = document.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.right_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)
    configure_styles(document)
    decimal_num = add_numbering(document, kind="decimal")
    bullet_num = add_numbering(document, kind="bullet")
    check_num = add_numbering(document, kind="check")
    header = section.header.paragraphs[0]
    header.alignment = WD_ALIGN_PARAGRAPH.LEFT
    header.paragraph_format.space_after = Pt(0)
    set_run_font(
        header.add_run("GODFIN  /  PRIVATE OWNER RUNBOOK"),
        size=8.5,
        color=MUTED,
        bold=True,
    )
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.paragraph_format.space_after = Pt(0)
    set_run_font(footer.add_run("Private & confidential  •  Page "), size=9, color=MUTED)
    add_field(footer, "PAGE")
    set_run_font(footer.add_run(" of "), size=9, color=MUTED)
    add_field(footer, "NUMPAGES")

    # Editorial-cover opening. Named override: owner_runbook_title.
    spacer = document.add_paragraph()
    spacer.paragraph_format.space_after = Pt(52)
    kicker = document.add_paragraph()
    kicker.alignment = WD_ALIGN_PARAGRAPH.CENTER
    kicker.paragraph_format.space_after = Pt(14)
    set_run_font(kicker.add_run("PRIVATE LAUNCH OPERATIONS"), size=10, color=BLUE, bold=True)
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    title.paragraph_format.space_after = Pt(10)
    set_run_font(
        title.add_run("GODFIN Owner\nCompletion Runbook"),
        size=28,
        color=NAVY,
        bold=True,
    )
    subtitle = document.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.paragraph_format.space_after = Pt(24)
    set_run_font(
        subtitle.add_run(
            "Owner-controlled credentials, signing, compliance, validation, and launch gates"
        ),
        size=13,
        color=DARK_BLUE,
    )
    metadata = document.add_paragraph()
    metadata.alignment = WD_ALIGN_PARAGRAPH.CENTER
    metadata.paragraph_format.space_after = Pt(42)
    set_run_font(
        metadata.add_run(
            "Version 3.4  •  31 August 2026  •  oculusrex14/GODFIN\n"
            "Beta website branch: codex/godfin-beta-website-v1"
        ),
        size=10,
        color=MUTED,
    )
    add_callout(
        document,
        "NON-NEGOTIABLE",
        "Never paste secrets, OAuth credentials, signing certificates, real statements, local databases, PINs, license keys, payout identities, or customer financial data into this document, source control, chat, tickets, or email.",
        tone="risk",
    )
    owner = document.add_paragraph()
    owner.alignment = WD_ALIGN_PARAGRAPH.CENTER
    owner.paragraph_format.space_before = Pt(20)
    set_run_font(
        owner.add_run("Owner: ______________________________    Target date: __________________"),
        size=10.5,
        color=INK,
    )

    document.add_page_break()
    document.add_heading("How to use this runbook", level=1)
    for item in (
        "Read the complete runbook once. Following the owner's preferred work order, finish local code, tests, documentation, and package checks first; then complete the provider/browser steps in Sections 1–4 as one final batch. Section 16 is always last.",
        "Use provider dashboards in your own browser. Store every secret only in the provider’s encrypted environment, GitHub Actions secret store, and your business password vault.",
        "Keep the desktop backend local. Supabase, Vercel, Cashfree, Resend, and R2 are website, licensing, email, and distribution services only; they must never become the application database.",
        "Do not enable checkout, the reward pilot, update-feed promotion, or public launch content until the matching sign-off gate is complete.",
        "When a step says “ask Codex to verify,” provide only the non-secret project name, public URL, or workflow run URL—not the credential value.",
    ):
        add_list_item(document, item, decimal_num)

    document.add_page_break()
    document.add_heading("Current verified state", level=1)
    add_callout(
        document,
        "ENGINEERING BASELINE",
        "Beta website engineering candidate c93c7fcd1f520f017e4f8e6b1241f49eff9fbbcc is pushed on codex/godfin-beta-website-v1. GitHub Actions run 33382231788 completed successfully against that exact commit on 31 August 2026. Its seven green jobs include the complete 1,011-test Python 3.12 backend suite, dependency and full-history secret audits, frontend and website production gates, deterministic Remotion media verification, desktop privacy/update audits, production smoke tests, Chromium/Firefox/WebKit accessibility and website matrices, and a clean 12-migration Supabase database with 146 passing pgTAP assertions. All 182 API operations retain the previously verified response contracts.",
        tone="good",
    )
    for item in (
        "Production repository URL: https://github.com/oculusrex14/GODFIN. It was made public only for the owner-requested CI window. Return it to PRIVATE immediately after the final documentation-only CI run; no public release or installer is authorized.",
        "Canonical production website: https://godfin.dev. The apex resolves to Vercel over HTTPS; https://godfin.vercel.app remains an operational fallback.",
        "Supabase project: GODFIN (ap-south-1). All 12 ordered migrations through 20260830044445_beta_waitlist_access_entitlements_feedback.sql align on the linked project. Clean CI passes all 146 pgTAP assertions for least-privilege grants, own-row RLS, two-user isolation, abuse controls, Cashfree state, upgrades, device caps, email leasing, beta invitations, phased entitlements, Gmail-test selection, checkout allowlisting, expiry, and feedback isolation. Managed backup/PITR, a restore drill, Auth leaked-password protection, and the real second-account browser flow remain required.",
        "Deprecated source is preserved only in private, read-only repository oculusrex14/GODFIN-OPUS46-ARCHIVE. Its 35-commit rewritten history and archival tag pass secret scanning; the obsolete local source/build workspace was moved to Trash while active Application Support data was preserved.",
        "PIN access recovery, portal-positioned calculation help, collapsible App Settings, external pricing navigation, auditable goal contributions, corrected goal simulation, recurring re-detection, atomic account routing, package privacy assertions, and the AY 2026–27 CA tax pack are implemented and tested.",
        "The beta website is deployed to production as Vercel deployment dpl_D7W9Gk172WWmM4zyxz7vJhkgK9do. godfin.dev is canonical and godfin.vercel.app remains the fallback. Public /demo and /how-it-works use one deterministic, fictional household; the static demo makes no finance-service requests and never presents upload or bank-connect controls. Public checkout remains closed. The double-opt-in early-tester form is enabled through verified Resend/DNS configuration and stores no desktop financial data.",
        "Production acceptance on 30 July 2026: website Playwright 4/4; Lighthouse performance 99, accessibility 100, SEO 100, LCP 1.73 seconds, CLS 0; required CSP, HSTS, frame, MIME, referrer, and permissions headers are present.",
        "Vercel already contains the Supabase public/server variables and LICENSE_SIGNING_SECRET. Values are encrypted and are intentionally not reproduced here.",
        "Google OAuth is active. The owner-controlled GODFIN Website project uses the rotated web client named GODFIN Website Rotated; the provider requests only openid/email/profile, the original client is revoked, and production sign-in returned successfully to /account twice on 30 July 2026.",
        "A non-revenue Max owner_test license is active for the owner account. The server stores only its hash, purchase history remains empty, and one macOS arm64 installation is verified through the normal three-device flow. The full key is retained only in macOS Keychain and encrypted local app storage.",
        "Dependency surfaces are separated into runtime, test, and frozen-build locks. The Gmail API client is an explicit runtime dependency. All four JavaScript workspaces and all three Python lock surfaces audit with no known vulnerability; cryptography is upgraded to the fixed 50.x line and the temporary exception has been removed.",
        "The deterministic CycloneDX 1.6 SBOM contains 1,035 unique components with zero unresolved license identifiers. Third-party notices list all conditional licenses. Final human legal clearance is intentionally fail-closed and remains pending in supply-chain/legal-clearance.json.",
        "Native GitHub Actions run 32823401864 built and launched unpacked packages from exact application candidate 5ee71fa on macOS arm64, Windows x64, and Linux x64. First starts were 2.098, 3.886, and 3.224 seconds; restarts were 2.440, 2.390, and 2.360 seconds; idle memory was 529.2, 488.1, and 498.5 MB. A separate isolated run on the owner's Apple Silicon Mac passed at 0.991 seconds first start, 0.822 seconds restart, and 598.8 MB. Every required run preserved its isolated synthetic database, enforced local trust and maintenance boundaries, and loaded request-only integrations after startup. Executable and log hashes are retained under docs/production-remediation/evidence. These packages were unsigned, not uploaded as installers, and not published. macOS x64/Intel is explicitly owner-deferred for this pass.",
        "Release workflows require exact tag, commit, and package-version agreement; refuse an existing GitHub Release; publish deterministic SBOM, notices, checksums, and provenance; use immutable action SHAs; and require staged promotion plus a reviewed rollback path.",
        "Beta website evidence is current through immutable commit c93c7fcd1f520f017e4f8e6b1241f49eff9fbbcc on codex/godfin-beta-website-v1. GitHub Actions run 33382231788 passed all seven jobs on that exact SHA, including all 1,011 backend tests, both three-engine browser matrices, deterministic media checks, and the clean 12-migration Supabase database matrix. Production acceptance then passed 24/24 checks across Chromium, Firefox, and WebKit on godfin.dev. This authorizes the tested beta website content only; it does not authorize an installer, payment acceptance, updater promotion, or public desktop launch.",
        "Desktop Gmail recovery is implemented and included in the exact-candidate native smoke packages. Its external-browser callback uses a short-lived signed handoff bound to the active desktop launch; ordinary routes still require the launch secret. The owner must start a completely fresh Connect Gmail attempt from an installed candidate; an old callback tab or stale OAuth state cannot be reused. oculusrexai@gmail.com and naraharikripa14@gmail.com are the intended Google test users. Connected status, first sync, restart, reauthorization, and the seven-day soak must be evidenced before this gate is complete.",
        "The local database upgraded from schema revision 21 to 22 with automatic pre-migration backup godfin_backup_20260824_034907_983690_e24b194b5f24.db. Integrity and foreign-key checks pass, and 100 reviewed canonical public-brand merchant aliases are indexed locally. The 24-partition synthetic enrichment benchmark reports 100% semantic accuracy, safety precision, UNKNOWN abstention, merchant auto-accept precision, relationship precision/recall, and balance-control accuracy, with approximately 1 ms p95 enrichment latency.",
        "Public Gmail consent-screen review, the fresh Gmail recovery/soak, Cashfree credentials plus sandbox/live webhook and refund tests, Supabase backup/PITR/restore and Auth leaked-password protection, the real second-account Google isolation flow, Apple/Windows certificates, R2, signed-installer and clean-system lifecycle evidence, dependency-license approval, independent parser/full pentesting, native assistive-technology checks, operational inbox testing, and public-launch authorization are not yet complete. Cashfree KYC and whitelisting are owner-confirmed complete. macOS x64/Intel is owner-deferred and must be reopened before any Intel support claim.",
        "Reward pilot, sponsor card, PPP checkout, and OpenDataLoader shipping remain safely feature-gated where applicable.",
    ):
        add_list_item(document, item, bullet_num)

    document.add_page_break()
    document.add_heading("Beta website, tester operations, and demo", level=1)
    add_callout(
        document,
        "PRODUCTION BETA WEBSITE",
        "Vercel deployment dpl_D7W9Gk172WWmM4zyxz7vJhkgK9do is Ready on godfin.dev. Public /demo requires no account, uses only static synthetic data, and makes no finance-service requests. Pricing is explicitly planned and public checkout is closed. The early-tester form is enabled with double opt-in through the verified godfin.dev Resend sending domain.",
        tone="good",
    )
    for item in (
        "Public routes verified with HTTP 200: /, /demo, /how-it-works, /pricing, /account, /privacy, /terms, and /docs. HSTS, CSP, frame denial, MIME protection, referrer policy, and permissions policy remain present.",
        "Production acceptance passed 24/24 across Chromium, Firefox, and WebKit: honest beta path, accessible video, reduced-motion fallback, auth-free static demo, narrow viewport, current support/non-goals, lifetime-only planned pricing, no public checkout, and representative accessibility checks.",
        "The additive migration 20260830044445_beta_waitlist_access_entitlements_feedback.sql is applied remotely. It adds selected-tester invitations, account-bound beta access, Core/Pro/Max phases, expiry, Gmail-test selection, controlled INR 1 checkout allowlisting, and isolated feedback without weakening the existing Cashfree verification path.",
        "The owner command surface is website/scripts/beta-ops.mjs. Run it from website with npm run beta:ops -- help. It can list confirmed/active candidates; shortlist, invite, activate, phase, pause, revoke, or complete access; manage Gmail-test and checkout allowlists; and inspect feedback. It never prints invite tokens, license keys, OAuth data, or service credentials.",
        "Normal progression is confirmed waitlist -> owner shortlist -> email invite -> matching Google account acceptance -> Core -> Pro -> Max. Waitlist membership alone grants nothing. INR 1 validation is a separate, private, owner-allowlisted checkout test for eligible active Max testers and is never public pricing or a normal purchase license.",
        "Generated media is reproducible from the isolated website/remotion project using Remotion 4.0.518 and React 19.1.9. It produces a 24-second 1920x1080 hero, a 54-second 1920x1080 walkthrough, an 18-second 1080x1920 social cut, WebM fallbacks, posters, captions, provenance hashes, decoded-frame checks, and privacy scans. Remotion is build tooling only and is not in the Next.js runtime bundle.",
        "Remotion's current Free License states that individuals and for-profit organizations with three or fewer people may create and automate videos. A team of four or more, or another covered collaboration, needs the applicable Company terms. The owner must confirm the correct tier with Remotion and counsel before ongoing production use. Codec patent obligations are separate and are not covered by Remotion's license. This is an engineering note, not legal advice.",
        "Resend is provisioned through the Vercel Marketplace, RESEND_API_KEY is encrypted, RESEND_FROM_EMAIL is GODFIN <hello@godfin.dev>, and the godfin.dev sending domain is verified. A production test completed form submission, confirmation redirect, and welcome-email queueing without exposing the token. Cashfree validation remains off until CASHFREE_CLIENT_ID and CASHFREE_CLIENT_SECRET are supplied and sandbox/live webhook gates pass. Beta download URLs remain unset until signed installers exist.",
    ):
        add_list_item(document, item, decimal_num)
    add_source(document, "Remotion pricing and license overview", "https://www.remotion.dev/docs/license/pricing")
    add_source(document, "Remotion license text", "https://github.com/remotion-dev/remotion/blob/main/LICENSE.md")
    add_source(document, "Remotion license FAQ", "https://www.remotion.dev/docs/license/faq")
    add_source(document, "Remotion current terms", "https://www.remotion.dev/docs/terms")
    add_owner_fields(document, ["Beta cohort owner", "Resend verification date", "Cashfree sandbox approval", "Completed by / date"])

    critical_path_heading = document.add_heading("Critical path and blockers", level=1)
    critical_path_heading.paragraph_format.page_break_before = True
    add_table(
        document,
        ["Blocker", "Why blocked", "Your intervention", "Completion evidence"],
        [
            ["GitHub Actions + repository privacy", "Run 33382231788 is green on exact beta SHA c93c7fc; the repository is public only for the owner-requested CI window.", "After the documentation-only final CI run is green, return the repository to private and verify with the GitHub API.", "All seven required jobs are green and repository visibility is PRIVATE."],
            ["Dependency legal review", "Automated license inventory is complete; human approval is not.", "Review conditional licenses and sign legal-clearance.json without changing evidence hashes.", "Release gate reports approved and the signed record is archived."],
            ["Cashfree India", "Repository integration, all 12 hosted migrations, database state-machine tests, private beta allowlisting, owner KYC, and provider whitelisting are complete; credentials, webhook, and sandbox/live transaction evidence are absent.", "Add CASHFREE_CLIENT_ID and CASHFREE_CLIENT_SECRET through Vercel; configure sandbox webhooks; keep public checkout disabled until the full sandbox and refund matrix passes.", "Replay-safe private INR 1 validation, purchase, upgrade, refund, dispute, rate-limit, and one-email flows pass."],
            ["Operational email completion", "Resend domain verification, DKIM/SPF sending records, encrypted Vercel variables, production double opt-in, and welcome-email queueing pass. DMARC policy, inbound hello@godfin.dev reply testing, a second mailbox provider, and ongoing monitoring remain owner operations.", "Send to and reply from hello@godfin.dev, add or verify DMARC, test a second provider, enable Resend account 2FA, and assign the monitored inbox owner.", "DMARC and inbox tests pass in two providers, replies work, and the support/privacy/security routing owner is recorded."],
            ["Provider callbacks", "The final domain and Vercel redirects are verified, but Google/Supabase and Cashfree must still be rechecked with their real provider settings.", "Set godfin.dev as the primary provider URL and retain the Vercel callback fallback.", "Google account return and Cashfree webhook/return URLs pass on godfin.dev."],
            ["Signing", "No GitHub signing secrets are configured.", "Complete Apple and Windows signing enrollment.", "Notarized/signed installers verify."],
            ["R2 updates", "No release bucket or releases.godfin.dev.", "Create R2, DNS, and least-privilege secrets.", "Immutable assets and updater metadata resolve."],
            ["Clean systems", "Exact-SHA unpacked smoke passes on macOS arm64, Windows x64, and Linux x64. Signed installer lifecycle acceptance remains on clean Apple Silicon, Windows x64, and Ubuntu x64 systems; Intel macOS is deferred.", "After signing credentials, release storage, and private signed builds are ready, run the install, upgrade, rollback, and data-recovery checks on clean systems for the three required platforms.", "Install/upgrade/recovery evidence is retained for the three required platforms."],
            ["Native browser and assistive technology", "Hosted Chromium, Firefox, and WebKit suites are green; native Safari/Edge and VoiceOver/NVDA/Orca acceptance still require supported systems.", "Run the manual native browser, keyboard, zoom, and screen-reader matrix on the exact signed packages.", "Screenshots, traces, accessibility results, and isolation evidence are archived."],
            ["Public launch", "Owner authorization has not been issued.", "Complete final gate and sign Section 16.", "Written authorization and release IDs."],
        ],
        [1500, 2100, 3000, 2760],
    )

    document.add_heading("1. Google OAuth through Supabase", level=1)
    add_callout(
        document,
        "BOUNDARY",
        "Google authentication is for website accounts and license management only. Do not request Gmail access here; the optional desktop Gmail integration is separate and local.",
        tone="info",
    )
    document.add_heading("1.1 Create the Google web client", level=2)
    add_callout(
        document,
        "CURRENT EVIDENCE",
        "Completed 30 July 2026. Dedicated Google Cloud project: GODFIN Website; project ID: godfin-website; project number: 173410737907. The active web client is GODFIN Website Rotated. Supabase Google authentication is enabled, the original client is revoked, and two production callback runs returned the owner account to /account. Do not reuse this website client for the optional desktop Gmail integration.",
        tone="good",
    )
    for item in (
        "Open Google Cloud Console in the business-owned project. Enable two-factor authentication for every administrator.",
        "Configure the OAuth consent screen. Use the final seller name, support email, privacy URL, terms URL, and verified domain. Choose the appropriate external/testing status for the launch stage.",
        "Request only openid, email, and profile through this website client. Do not add Gmail or finance scopes.",
        "Create an OAuth 2.0 Client ID of type Web application.",
        "Add authorized JavaScript origins: https://godfin.dev and https://www.godfin.dev. Keep https://godfin.vercel.app only as the documented operational fallback while migration is completed.",
        "In Supabase Dashboard → Authentication → Providers → Google, copy the exact callback URL. For this project it follows https://omrtkfwjauyakhvynutk.supabase.co/auth/v1/callback. Add that exact value as the Google authorized redirect URI.",
        "Copy the client ID and client secret directly from Google into the Supabase Google provider form. Do not download or commit a client-secret JSON file.",
    ):
        add_list_item(document, item, decimal_num)
    document.add_page_break()
    document.add_heading("1.2 Configure and test Supabase", level=2)
    for item in (
        "In Supabase Authentication → URL Configuration, set Site URL to https://godfin.dev.",
        "Add https://godfin.dev/auth/callback and https://www.godfin.dev/auth/callback to the redirect allow-list. Retain https://godfin.vercel.app/auth/callback as the explicit fallback.",
        "Enable the Google provider and save.",
        "Open https://godfin.dev/account in a private browser window, choose Google, complete consent, and verify return to /account.",
        "Sign out and repeat with naraharikripa14@gmail.com. Confirm neither account can see the other account’s purchases, licenses, activations, or waitlist data.",
        "Review Supabase Auth logs for redirect, consent, or email mismatch errors. Remove obsolete test clients when verification is complete.",
    ):
        add_list_item(document, item, decimal_num)
    add_source(document, "Supabase Google authentication guide", "https://supabase.com/docs/guides/auth/social-login/auth-google")
    for item in (
        "Google login succeeds from a private window.",
        "The account page shows the signed-in email and no other user’s data.",
        "Only openid/email/profile consent appears.",
        "The client secret exists only in Google/Supabase and the business vault.",
    ):
        add_list_item(document, item, check_num)
    add_callout(
        document,
        "VERIFIED",
        "The canonical origin is https://godfin.dev, the Supabase provider callback is https://omrtkfwjauyakhvynutk.supabase.co/auth/v1/callback, and the website callback is https://godfin.dev/auth/callback. The Vercel callback remains a fallback. A distinct second-account isolation test remains a pre-launch gate.",
        tone="good",
    )
    add_owner_fields(document, ["Google OAuth client name", "Test accounts used", "Completed by / date"])

    document.add_page_break()
    document.add_heading("1.3 Desktop Gmail OAuth for local ingestion", level=2)
    add_callout(
        document,
        "SEPARATE CLIENT AND SCOPE",
        "This is not the website Google login. Create a dedicated OAuth client of type Desktop app and request only https://www.googleapis.com/auth/gmail.readonly. GODFIN cannot send, edit, or delete email through this integration.",
        tone="warn",
    )
    add_callout(
        document,
        "IF YOU SAW MISSING_LAUNCH_TRUST",
        "Fully quit GODFIN, reopen /Applications/GODFIN.app, and begin a fresh Connect Gmail attempt from Settings. Do not reuse or refresh an old Google callback tab. Candidate 5ee71fa uses a short-lived signed, nonce-bearing OAuth handoff bound to the active desktop launch; every ordinary backend route still requires the active launch secret. Complete this check only on an installed package built from that exact application candidate or a later documentation-only descendant; the hosted unpacked smoke does not authorize Gmail access on the owner installation.",
        tone="info",
    )
    for item in (
        "In a business-owned Google Cloud project dedicated to GODFIN Desktop Gmail, enable the Gmail API and configure the OAuth consent screen. Keep its client, scopes, and consent records separate from the GODFIN Website web client.",
        "Create an OAuth 2.0 Client ID of type Desktop app. Download the JSON and confirm its top-level object is installed and contains client_id and client_secret. Do not use a Web application JSON file.",
        "The local callback is http://127.0.0.1:5100/api/v1/auth/gmail/callback. GODFIN binds the backend to localhost by default; do not expose this callback or backend to the public internet.",
        "Move the downloaded JSON outside the repository into an owner-controlled Application Support location. Point GODFIN_GMAIL_CLIENT_SECRETS_FILE to that absolute file. For development only, backend/data/client_secret.json is supported but must remain ignored and must never be committed, attached, or shared.",
        "Alternatively set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the private local process environment. Never put either value in source files, screenshots, this runbook, terminal history, or chat.",
        "Start GODFIN, open Settings, choose Connect Gmail, and select either listed test user. Review the Google consent screen. It must show read-only Gmail access and no send, modify, delete, contacts, Drive, calendar, or broad Google account scope.",
        "Complete the localhost callback. The exact external-browser GET callback succeeds only when its short-lived signed state proves the active GODFIN launch; host/origin validation, nonce, one-time use, session binding, and expiry remain enforced. Verify Settings changes to connected, run the initial sync against a test mailbox, and confirm imports are assigned only to configured active account routes.",
        "Disconnect Gmail, confirm the local token is removed, then reconnect and verify reauthorization. Tokens are encrypted in GODFIN's local app storage using its stable local key; OAuth state is signed, launch-bound, expiring, and single-use.",
        "If the browser shows invalid_state, MISSING_LAUNCH_TRUST, or an old GODFIN error page, close that tab, return to Settings, and choose Connect Gmail again. Do not refresh the failed callback. If the new attempt still fails, record only the error code and time; never share the authorization code, client secret, or token.",
        "While Google keeps the app in Testing, retain oculusrexai@gmail.com and naraharikripa14@gmail.com as test users and record the expiry/re-consent implications. Complete Google verification before inviting general customers if the provider requires it for the read-only scope.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Dedicated Desktop app client exists; the website client is not reused.",
        "Only gmail.readonly appears on the consent screen.",
        "The downloaded client JSON is outside the repository and protected by owner-only permissions.",
        "Connect, localhost callback, connected status, initial sync, disconnect, and reauthorization pass.",
        "No client secret or token appears in Git, logs, screenshots, chat, or the packaged application.",
    ):
        add_list_item(document, item, check_num)
    add_source(document, "Google Gmail API Python quickstart", "https://developers.google.com/workspace/gmail/api/quickstart/python")
    add_owner_fields(document, ["Google Cloud project name", "Desktop OAuth client name", "Test mailbox", "Completed by / date"])

    document.add_heading("2. Cashfree India: one-time payments only", level=1)
    add_callout(
        document,
        "HARD RULE",
        "Sell only the Pro and Max lifetime licenses. They include zero hosted AI credits. Do not create subscriptions, trials, recurring prices, credit packs, or monthly allowances.",
        tone="risk",
    )
    document.add_heading("2.1 Complete the business account", level=2)
    add_callout(
        document,
        "OWNER-CONFIRMED PROVIDER STATE",
        "Cashfree KYC and merchant whitelisting are complete as confirmed by the owner on 31 August 2026. GODFIN still keeps checkout disabled because CASHFREE_CLIENT_ID and CASHFREE_CLIENT_SECRET are not present in Vercel and the sandbox/live webhook, refund, dispute, invoice, and tax evidence below has not been executed.",
        tone="warn",
    )
    for item in (
        "Use a Cashfree account owned by the legal seller. Complete Payment Gateway activation, KYC, bank verification, statement descriptor, customer support details, tax settings, and two-factor authentication.",
        "Invite a backup administrator with the minimum role needed. Do not share one login.",
        "Confirm with Cashfree and your tax adviser that the account may sell one-time software licenses domestically and internationally, and how GST, invoices, chargebacks, and refunds must be handled.",
        "Enable Cashfree's available risk controls. Do not build hardware serial, persistent IP fingerprint, or payment-method fingerprint storage in GODFIN.",
    ):
        add_list_item(document, item, decimal_num)
    document.add_heading("2.2 Verify all 12 Supabase migrations and recovery", level=2)
    add_callout(
        document,
        "DO THIS BEFORE ENABLING CHECKOUT",
        "All 12 migrations now align remotely and clean CI passes 146 assertions. Keep CHECKOUT_ENABLED=false throughout this section. Backup/PITR, a restore drill, leaked-password protection, and provider sandbox evidence still block checkout.",
        tone="warn",
    )
    for item in (
        "Repository evidence already retained: GitHub Actions run 33382231788 applied all 12 migrations to a clean temporary database and passed all 146 pgTAP assertions on exact beta website candidate c93c7fc. Do not replace this with source inspection.",
        "Linked-project evidence: all 12 local/remote migration versions align through 20260830044445_beta_waitlist_access_entitlements_feedback.sql. The previous 11-migration evidence remains under docs/production-remediation; retain the new CLI alignment output with the beta tranche evidence.",
        "In Supabase Dashboard, open GODFIN → Database → Backups. Current evidence shows no managed backup history and PITR disabled. Upgrade the plan or create an approved encrypted export before checkout, then perform and document a restore drill.",
        "In Supabase Dashboard, open Authentication → Settings or Security and enable leaked-password protection if the current plan offers it. The Auth advisor currently reports it disabled. Do not mark this complete until the advisor is clean.",
        "Use a second Google test account to sign in to godfin.dev. Confirm each account sees only its own licenses, purchases, and activations. Database-level two-user isolation already passes; this step validates the browser/provider path.",
        "Back in Terminal, run: supabase login. Complete the one-time browser authorization if asked; never paste the access token into this document or chat.",
        "Run: supabase link --project-ref omrtkfwjauyakhvynutk. Confirm the displayed project is GODFIN in ap-south-1.",
        "Run: supabase migration list --linked. Confirm all 12 names appear in both local and remote columns, ending with 20260830044445_beta_waitlist_access_entitlements_feedback.sql.",
        "For any future pending migration, run supabase db push --linked --dry-run first and confirm the exact proposed files. Take the approved backup/export before the real push.",
        "After any future migration, rerun the isolated CI database job and all five linked-project pgTAP files. A source parse is not a database pass.",
        "Leave CHECKOUT_ENABLED=false until backup/restore, Auth, second-account, Cashfree sandbox, and qualified tax/refund gates all pass.",
    ):
        add_list_item(document, item, decimal_num)
    add_source(document, "Supabase database migrations", "https://supabase.com/docs/guides/deployment/database-migrations")

    document.add_heading("2.3 Configure sandbox variables and catalog", level=2)
    add_table(
        document,
        ["Setting", "Purpose", "Safe starting value", "Owner action"],
        [
            ["CASHFREE_CLIENT_ID", "Server authentication", "Secret; leave blank in Git", "Add sandbox value in Vercel Preview"],
            ["CASHFREE_CLIENT_SECRET", "Webhook/API HMAC secret", "Secret; leave blank in Git", "Add sandbox value in Vercel Preview"],
            ["CASHFREE_ENVIRONMENT", "Provider environment", "sandbox", "Change only after live acceptance"],
            ["CHECKOUT_ENABLED", "Global checkout kill switch", "false", "Enable only for a controlled test"],
            ["PPP_CHECKOUT_ENABLED", "Regional pricing gate", "false", "Keep off until global legal/tax review"],
            ["CASHFREE_GLOBAL_PAYMENTS_APPROVED", "Owner approval for global checkout", "false", "Set true only with documented approval"],
        ],
        [2800, 2500, 1600, 2460],
    )
    for item in (
        "The authoritative server catalog remains Pro ₹4,999 and Max ₹9,999. Both are one-time lifetime licenses and include no hosted AI credits.",
        "Add sandbox credentials to Vercel Preview first. Keep production credentials in a separate environment and business vault.",
        "Leave PPP_CHECKOUT_ENABLED=false. India remains the only enabled checkout region until Cashfree international-payment approval, billing-country evidence, and qualified legal/tax review are complete.",
        "Do not pass amount, currency, country, user ID, or entitlement from browser code. GODFIN selects and revalidates them server-side.",
        "All 12 ordered Supabase migrations are applied. Keep CHECKOUT_ENABLED=false until recovery/Auth and the complete Cashfree sandbox matrix below pass.",
    ):
        add_list_item(document, item, decimal_num)
    document.add_heading("2.4 Configure the webhook", level=2)
    for item in (
        "In Cashfree's sandbox dashboard, open Developers → Webhooks (the wording may be Payment Gateway → Webhooks), choose Add webhook, and enter https://godfin.dev/api/webhook. Retain the Vercel fallback only while canonical migration is being verified.",
        "Subscribe to PAYMENT_SUCCESS, PAYMENT_FAILED, PAYMENT_USER_DROPPED, refund/auto-refund status, and dispute created/updated/closed events.",
        "Choose the latest available webhook version supported by the account. This build sends Cashfree API version 2025-01-01 and accepts signed webhooks using 2025-01-01 or the legacy 2023-08-01 version. Do not change the version without updating the provider contract tests.",
        "Cashfree signs the timestamp plus the exact raw body with HMAC-SHA256. Do not add a second parser/proxy that reformats the body before GODFIN verifies it.",
        "Use Cashfree Dashboard webhook replay to send the same paid event twice. Verify one provider event, one purchase, one license, and one email.",
    ):
        add_list_item(document, item, decimal_num)
    document.add_heading("2.5 Payment acceptance evidence", level=2)
    for item in (
        "Unauthenticated checkout returns a sign-in requirement.",
        "Successful Pro and Max sandbox payments provision exactly one lifetime license each.",
        "Invalid webhook signatures return HTTP 400 and create nothing.",
        "Cancelled, failed, dropped, or unpaid orders create no license.",
        "A browser return without a verified success webhook creates no license.",
        "A partial refund suspends; a full refund revokes; a merchant-won dispute restores only when no other adverse state exists.",
        "An auto-refund for a different payment attempt on the same order does not affect the paid license.",
        "The desktop fourth activation is rejected; deactivating one device allows another.",
        "A controlled live purchase is completed only after legal, tax, email, and refund procedures are ready.",
    ):
        add_list_item(document, item, check_num)
    add_source(document, "Cashfree current Payments API", "https://www.cashfree.com/docs/api-reference/payments/latest/overview")
    add_owner_fields(document, ["Cashfree merchant ID (not keys)", "Sandbox webhook name", "Live webhook name", "Completed by / date"])

    document.add_heading("3. Resend, operational email, and DNS", level=1)
    add_callout(
        document,
        "CURRENT VERIFIED EMAIL STATE",
        "Vercel Marketplace resource resend-email-citron-mountain is active. Resend domain godfin.dev is Verified; its DKIM and SPF sending records resolve publicly; Hostinger retained automatic DNS snapshot 176973183; and Vercel stores RESEND_API_KEY plus RESEND_FROM_EMAIL=GODFIN <hello@godfin.dev> as encrypted variables. Production form submission, single-use confirmation redirect, and welcome-email queueing pass. No secret or confirmation token is reproduced here.",
        tone="good",
    )
    for item in (
        "Confirm hello@godfin.dev is a real receiving mailbox or forwarding address. Resend sends application email; it is not the support inbox. Send a message to hello@godfin.dev from an unrelated account and reply from it before continuing.",
        "Confirm the Resend account remains under the business owner and enable two-factor authentication if it is not already active.",
        "Preserve the verified SPF and DKIM records. Do not invent a second SPF policy or replace the existing Hostinger mailbox MX records.",
        "Add a DMARC record. Start with monitoring if necessary, review reports, then tighten with counsel/operations guidance.",
        "Create and monitor hello@godfin.dev as the single general-purpose address for license delivery, customer support, privacy/legal requests, and security reports. Use inbox labels or filters so each request type remains easy to track.",
        "Keep the least-privilege production Resend key only in the Vercel Marketplace integration. Keep RESEND_FROM_EMAIL as GODFIN <hello@godfin.dev>, NEXT_PUBLIC_SUPPORT_EMAIL as hello@godfin.dev, and NEXT_PUBLIC_PRIVACY_EMAIL as hello@godfin.dev; never export or print the key.",
        "Repeat the production waitlist test after any email or database change. Confirm once and verify a repeated confirmation does not duplicate the record.",
        "Complete a synthetic license email test to Gmail and another provider. Check SPF, DKIM, DMARC alignment, inbox placement, links, mobile layout, plain-text fallback, reply path, and resend behavior.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Resend domain shows Verified.",
        "SPF, DKIM, and DMARC checks pass.",
        "Double-opt-in waitlist works and stores no desktop financial data.",
        "License delivery works in two mailbox providers.",
        "hello@godfin.dev is monitored and its support, privacy/legal, license, and security filters are tested.",
    ):
        add_list_item(document, item, check_num)
    add_source(document, "Resend domain verification", "https://resend.com/docs/dashboard/domains/introduction")
    add_owner_fields(document, ["DNS provider", "Second test mailbox provider", "Support owner", "Completed by / date"])

    document.add_heading("4. Domain and Vercel production", level=1)
    add_callout(
        document,
        "CURRENT DOMAIN CHECK",
        "On 31 August 2026, exact candidate c93c7fc was deployed as production deployment dpl_D7W9Gk172WWmM4zyxz7vJhkgK9do. https://godfin.dev and https://godfin.vercel.app return HTTP 200; https://www.godfin.dev uses the production alias; HSTS and the Cashfree-only CSP are present; 24/24 public checks pass across Chromium, Firefox, and WebKit; media byte ranges return 206; and no runtime errors were reported. Public checkout is closed and the double-opt-in early-tester form is enabled.",
        tone="good",
    )
    for item in (
        "Register or confirm control of godfin.dev in a business-owned registrar account. Enable registrar lock, two-factor authentication, auto-renewal, and a recovery contact.",
        "In Vercel project godfin, add godfin.dev and www.godfin.dev. Copy only the DNS records Vercel displays into the authoritative DNS provider.",
        "Choose one canonical host. Redirect the other host permanently.",
        "NEXT_PUBLIC_SITE_URL=https://godfin.dev is already set for Production, Preview, and Development. Keep Google/Supabase redirect allow-lists and the Cashfree webhook/return URLs synchronized with the final domain.",
        "Open Terminal and run: cd /Users/oculus/Projects/GODFIN/.codex-godfin-v6/website. Then run: vercel whoami. If it asks you to sign in, run vercel login, complete the browser approval yourself, and return to Terminal.",
        "Run: vercel link. Select the existing GODFIN team/account and the existing godfin project. Do not create a second Vercel project.",
        "Run: vercel env ls. The public domain/email variables, Supabase variables, Resend integration variables, abuse secret, license-signing and entitlement keys, CASHFREE_ENVIRONMENT=sandbox, CHECKOUT_ENABLED=false, PPP_CHECKOUT_ENABLED=false, and CASHFREE_GLOBAL_PAYMENTS_APPROVED=false are already present. Add the still-missing CASHFREE_CLIENT_ID and CASHFREE_CLIENT_SECRET only through Vercel's encrypted environment UI or prompt; never print or commit their values. Add beta download URLs only after signed installers exist.",
        "Production deployment dpl_D7W9Gk172WWmM4zyxz7vJhkgK9do is intentionally fail-closed for public checkout. After any provider-variable change, keep CHECKOUT_ENABLED=false, deploy a preview from the exact candidate, and retest account sign-in, pricing, disabled checkout behavior, waitlist confirmation, privacy, terms, and license verification.",
        "All 12 Supabase migrations are applied and database-tested. After recovery/Auth and the Cashfree sandbox matrix pass, run the repository website checks again and deploy the exact tested SHA to production. A production deployment does not authorize customer checkout or the public desktop launch.",
        "Verify HTTPS, HSTS, CSP, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy, sitemap.xml, robots.txt, and a deliberate 404.",
        "Set immutable signed download URLs only after Section 12 clean-system validation. Do not point download buttons at unsigned local builds.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Apex and www resolve as designed over HTTPS.",
        "Account, pricing, download, privacy, terms, docs, waitlist, and callback paths pass.",
        "Google, Cashfree, and Resend use the canonical production host.",
        "No secret appears in build logs or browser JavaScript.",
    ):
        add_list_item(document, item, check_num)
    add_owner_fields(document, ["Registrar", "Renewal date", "Canonical host", "Completed by / date"])

    document.add_page_break()
    document.add_heading("5. License custody and three-device operations", level=1)
    add_callout(
        document,
        "CURRENT STATE",
        "LICENSE_SIGNING_SECRET is already present as an encrypted Vercel variable. Do not replace it casually: issued keys are derived from it. The database stores license hashes, not full license keys.",
        tone="warn",
    )
    for item in (
        "Confirm the exact current LICENSE_SIGNING_SECRET is stored in the business password vault with restricted access and a tested offline recovery copy. Never reveal the value.",
        "Record authorized custodians and an emergency access procedure.",
        "Use random installation IDs stored in OS secure storage. Do not add hardware serials, payment details, or persistent IP fingerprints.",
        "From a paid test account, activate three synthetic installations. Confirm a fourth returns ACTIVATION_LIMIT.",
        "Open /account, list the devices, deactivate one, and verify a new installation can activate.",
        "Verify offline grace, re-verification, invalid key, inactive license, lost-key resend, and local license removal. Confirm local financial data remains untouched.",
        "Before any future secret rotation, design versioned key IDs, legacy verification, reissue, rollback, and customer communication.",
        "Completed 30 July 2026: the owner license is kind owner_test, tier Max, linked to the owner’s Supabase account, absent from purchase/revenue records, stored only as a hash server-side, and activated on one macOS arm64 installation through the normal verification flow. Its full key is not reproduced in this document.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Vault and offline recovery copies are verified.",
        "Three active installations succeed; the fourth is blocked.",
        "Account-based deactivation and replacement succeed.",
        "No serial, IP fingerprint, payment method, or financial ledger is stored by licensing.",
    ):
        add_list_item(document, item, check_num)
    add_owner_fields(document, ["Vault record name (not the value)", "Authorized custodians", "Completed by / date"])

    document.add_heading("6. macOS signing and notarization", level=1)
    for item in (
        "Enroll the legal seller in the Apple Developer Program and complete identity verification.",
        "Create a Developer ID Application certificate for distribution outside the Mac App Store.",
        "Install the certificate and private key on a secured Mac, export a password-protected .p12, and store it only in the business vault.",
        "Create an Apple app-specific password for notarization and record the Team ID.",
        "Add GitHub Actions secrets MAC_CSC_LINK, MAC_CSC_KEY_PASSWORD, APPLE_ID, APPLE_APP_SPECIFIC_PASSWORD, and APPLE_TEAM_ID. Values must never appear in logs.",
        "Run the private release workflow. Verify code signature, hardened runtime, entitlements, Electron fuses, notarization, stapling, DMG, and ZIP update artifact.",
        "Install on clean macOS 13+ Apple silicon and Intel systems with Gatekeeper enabled. Do not instruct users to bypass Gatekeeper.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "codesign --verify succeeds.",
        "spctl assessment succeeds.",
        "stapler validate succeeds.",
        "Clean Apple silicon and Intel installs launch without override.",
    ):
        add_list_item(document, item, check_num)
    add_owner_fields(document, ["Apple Team ID", "Certificate expiry", "Workflow run URL", "Completed by / date"])

    document.add_page_break()
    document.add_heading("7. Windows signing", level=1)
    for item in (
        "Purchase an Authenticode certificate in the legal seller’s name from a trusted provider. Prefer the provider’s supported hardware- or cloud-protected signing workflow.",
        "Complete identity verification and document who controls signing access.",
        "If the CI path supports an exportable PFX, store the protected file in the vault and add WIN_CSC_LINK and WIN_CSC_KEY_PASSWORD to GitHub Actions secrets.",
        "Require a trusted timestamp so signatures remain valid after certificate expiry.",
        "Build the private draft Windows installer. Verify publisher, chain, timestamp, NSIS behavior, and retained app data.",
        "Install on clean Windows 10 22H2 and Windows 11 x64 systems with SmartScreen enabled. Record reputation warnings separately from signature validity.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Signature and timestamp verify.",
        "Publisher matches the legal seller.",
        "Windows 10 and 11 clean installs pass.",
        "Upgrade and uninstall preserve SQLite data unless the user explicitly deletes it.",
    ):
        add_list_item(document, item, check_num)
    add_owner_fields(document, ["Certificate provider", "Certificate expiry", "Workflow run URL", "Completed by / date"])

    document.add_page_break()
    document.add_heading("8. Cloudflare R2 and signed updates", level=1)
    for item in (
        "Create a business-owned Cloudflare account, enable two-factor authentication, and create an R2 bucket dedicated to release artifacts only.",
        "Connect releases.godfin.dev to the bucket and verify HTTPS. Do not place customer data or desktop backups in this bucket.",
        "Create a least-privilege R2 API token for release automation. Add GitHub secrets R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID, and R2_RELEASE_BUCKET.",
        "Keep release binaries under immutable versioned paths such as /v0.1.0/<artifact>. Never overwrite a released binary.",
        "Verify Content-Type, Content-Disposition, range requests, checksums, blockmaps, and architecture-specific latest metadata.",
        "For the first 5% update cohort, the promote-updates workflow requires PUBLISH_STAGED_RELEASE. Advancing to 25%, 50%, or 100% requires ADVANCE_AFTER_HEALTH_REVIEW. Both use the protected release-production environment and must not run before explicit public-launch authorization.",
        "Test rollback with a previously reviewed signed release using the separate rollback workflow and the exact confirmation ROLLBACK_SIGNED_RELEASE.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Anonymous read works; list/write does not.",
        "Versioned assets are immutable.",
        "SHA-256 checksums match a fresh download.",
        "Updater detects the correct OS/architecture artifact.",
        "Rollback metadata restores the reviewed previous version.",
    ):
        add_list_item(document, item, check_num)
    add_owner_fields(document, ["R2 account ID (not secret)", "Bucket", "Update domain", "Completed by / date"])

    document.add_heading("9. Market-data access for Max net worth", level=1)
    add_callout(
        document,
        "KEY CUSTODY",
        "GODFIN does not need a shared Twelve Data key. Each user supplies a key that is encrypted locally and sent only to Twelve Data when that user requests a quote.",
        tone="good",
    )
    for item in (
        "Review Twelve Data’s current plans, market coverage, attribution, caching, redistribution, and rate-limit terms with counsel or a responsible product owner.",
        "Define the supported liquid instruments and symbol format in support documentation. Do not promise universal coverage or uninterrupted quotes.",
        "Test stock, ETF, mutual-fund, crypto, bond, metal, and currency-conversion requests with a personal test key. Never place that key in Vercel, GitHub, screenshots, or fixtures.",
        "Verify missing, expired, rate-limited, invalid, and unavailable quotes show a recoverable error and never break manual assets or authoritative totals.",
        "Confirm land, property, gems, private assets, and unsupported instruments always require user-entered source, valuation date, and review/expiry date.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Terms and support scope reviewed.",
        "A test key works and remains encrypted locally.",
        "Quote failure leaves manual calculations usable.",
        "Freshness, provenance, currency, and expiry are visible.",
    ):
        add_list_item(document, item, check_num)
    add_source(document, "Twelve Data API documentation", "https://twelvedata.com/docs")
    add_owner_fields(document, ["Reviewer", "Supported-market decision date", "Completed by / date"])

    document.add_page_break()
    document.add_heading("10. Reward-pilot privacy, payouts, and controls", level=1)
    add_callout(
        document,
        "SAFE DEFAULT",
        "Keep reward_pilot disabled for launch unless every step below is complete. The ₹50,000 pilot is separate consent, off by default, and is not required for GODFIN’s core product.",
        tone="warn",
    )
    for item in (
        "Obtain written privacy and legal review of consent, participant eligibility, withdrawal, retention, cross-border processing if any, payout tax treatment, and incident response.",
        "Approve the fixed economics: ₹100 for the first accepted 90-day aggregate bundle; ₹25 per net-new verified template family up to six; ₹10 per material variant up to five; maximum ₹300 per participant and ₹50,000 overall.",
        "Fund a dedicated pilot payout budget and define who approves submissions, disputes, duplicate detection, and payouts.",
        "Deploy a dedicated HTTPS ingestion endpoint. Configure GODFIN_REWARD_PILOT_URL only in a controlled candidate build. Never accept HTTP.",
        "Keep payout identity in a separate access-controlled system from pseudonymized contributions. Define the linking token, access log, retention, and deletion process.",
        "Use the local preview/redaction screen before submission. Reject names, account/card numbers, UPI/VPA, emails, phones, addresses, exact dates, exact amounts, balances, transaction descriptions, and raw statements.",
        "Red-team the endpoint with synthetic identifiers and malformed payloads. Confirm the server rejects forbidden fields and the pilot cap cannot be exceeded under concurrency/retry.",
        "Run a small internal dry run, reconcile accepted bundles to payouts, delete test identities, and obtain written approval before enabling the feature flag.",
    ):
        add_list_item(document, item, decimal_num)
    document.add_page_break()
    for item in (
        "Legal/privacy review signed.",
        "₹50,000 cap and ₹300 participant cap are enforced server-side.",
        "Payout identity is separate from contribution data.",
        "Redaction rejection tests pass.",
        "Consent version, preview, withdrawal, retention, and audit evidence pass.",
        "Feature remains off until written enablement approval.",
    ):
        add_list_item(document, item, check_num)
    add_owner_fields(document, ["Pilot legal reviewer", "Payout owner", "Endpoint public hostname", "Approval date"])

    document.add_heading("11. OpenDataLoader benchmark decision", level=1)
    for item in (
        "Leave opendataloader_benchmark disabled in customer builds.",
        "Lawfully assemble 200–500 privacy-safe, redacted statement fixtures covering supported formats and known failure modes. Do not use customer files without specific permission.",
        "Manually label required fields and reconciliation totals. Record source format, parser outcome, manual corrections, runtime, and memory without storing financial identifiers.",
        "Provide Java 11+ only in the isolated benchmark environment; do not silently add a Java dependency to customer packaging.",
        "Run the current extractor and OpenDataLoader adapter on the same corpus. The decisive metric is complete reconciliation without manual correction, followed by field accuracy, runtime, memory, packaging size, and failure clarity.",
        "Ship only if the measured accuracy gain justifies Java packaging and all supported OS installers pass. Otherwise document the decision and retain the current extractor.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Corpus is lawfully sourced and fully redacted.",
        "Labels and reconciliation totals are independently reviewed.",
        "Both extractors run on identical fixtures.",
        "Ship/no-ship decision and evidence are archived.",
    ):
        add_list_item(document, item, check_num)
    add_owner_fields(document, ["Corpus owner", "Fixture count", "Decision", "Completed by / date"])

    document.add_heading("12. Clean-system packaging and recovery matrix", level=1)
    add_table(
        document,
        ["Platform", "Install", "Upgrade", "Offline", "Data/key preserved", "Uninstall", "Evidence"],
        [
            ["macOS 13+ arm64", "☐", "☐", "☐", "☐", "☐", ""],
            ["macOS 13+ x64 (owner-deferred)", "—", "—", "—", "—", "—", "Reopen before any Intel support claim"],
            ["Windows 10 22H2 x64", "☐", "☐", "☐", "☐", "☐", ""],
            ["Windows 11 x64", "☐", "☐", "☐", "☐", "☐", ""],
            ["Ubuntu 22.04 x64", "☐", "☐", "☐", "☐", "☐", ""],
        ],
        [1800, 750, 950, 850, 1300, 1000, 2710],
    )
    for item in (
        "Snapshot the clean system, install the signed candidate, set a synthetic PIN, import a redacted fixture, classify one item, create a backup, and record database path and app version.",
        "Restart online and offline. Confirm localhost binding, no cloud ledger, correct session behavior, encrypted secrets, and deterministic operation without AI.",
        "If Ollama is absent, confirm GODFIN opens the official installer and never silently installs. Test no-AI mode. On capable hardware, test the recommended signed-registry model path.",
        "Upgrade from the previous candidate. Confirm SQLite, encryption key, installation ID, license, settings, merchant memory, backup history, and reports remain valid.",
        "Exercise rollback and restore on a copy. Confirm pre-migration backup and restart-safe additive migrations.",
        "Uninstall using the platform default. Confirm application data is retained unless the user explicitly chooses deletion; document the manual removal path.",
        "Record cold start, common navigation p95, 10,000-row filter, 1,000-row import, and idle memory against the committed performance budgets. Reject accepted-baseline regression above 15%.",
    ):
        add_list_item(document, item, decimal_num)
    add_owner_fields(document, ["Test coordinator", "Candidate version", "Evidence folder", "Completed by / date"])

    document.add_page_break()
    document.add_heading("13. Security, privacy, payment, and recovery evidence", level=1)
    for item in (
        "Backend: all 1,011 tests passed in GitHub Actions run 33382231788 under clean Python 3.12 on exact beta website candidate c93c7fc, including auth/PIN, encryption, migrations, backups, merchant upsert, licenses, local trust, Gmail coverage/restart handling, startup dependency boundaries, exact response contracts for all 182 API operations, certified statement parsers, hostile-file preflight, goal/simulation/recurring behavior, CA tax pack, classification memory, performance, net worth, behavior insights, reward-pilot redaction, and UTC finance-fetch regressions.",
        "Independent finance oracle: golden_ledger_v1.json is evaluated by a standard-library-only oracle that imports no application calculation code. Dashboard, transactions, cash flow, FY reports, encrypted CA pack, income, profile, subscriptions, goals, net worth, audit aggregates, and AI non-authority agree with the independently expected values.",
        "Private parser fixtures: owner-supplied SBI, HDFC, and Kotak PDFs are recognized as sbi_savings, hdfc_savings, and kotak_savings and reconcile exactly to 29, 306, and 497 rows. Only hashes and aggregate evidence are retained; the PDFs are not copied into the repository.",
        "Frontend: lint, static accessibility/contrast, memory-only authentication, build-identity, secure-password, tier-navigation, and production-build gates pass. The deterministic inventory records 422 controls across 19 route scopes. GitHub Actions run 33382231788 also passed the production smoke and accessibility suites in Chromium, Firefox, and WebKit, including focus restoration during idle upload progress ticks; native screen-reader and signed-package interaction remain separate gates.",
        "Website: beta access, invitation identity binding, private INR 1 allowlisting, entitlement/payment contracts, Cashfree signature/idempotency, 12 ordered migration hashes, deterministic Remotion rendering and media verification, production build, auth-free static demo, reduced-motion fallbacks, planned lifetime/no-bundled-credit pricing, security headers, no public checkout, double-opt-in waitlist, and dependency audit pass. A clean Supabase stack passes all 146 pgTAP assertions. Production acceptance passed 24/24 across Chromium, Firefox, and WebKit on godfin.dev. A controlled signup returned HTTP 200, its single-use confirmation returned HTTP 307 to /waitlist/confirmed, and both confirmation and welcome messages entered Resend's delivery queue.",
        "Dependencies: runtime, test, and build Python locks are separated and hash-locked; frontend, website, desktop, and Playwright workspaces use npm ci. Audits report zero unaccepted known vulnerabilities. The Gmail API client is explicit in runtime requirements.",
        "Supply chain: deterministic CycloneDX 1.6 SBOM and third-party notices cover 1,035 unique components with zero unresolved license identifiers. Human review of conditional licenses remains a required fail-closed release gate.",
        "Release engineering: 12/12 desktop update/release workflow tests and 11/11 package privacy checks pass. All GitHub Actions are pinned to verified 40-character commit SHAs, checksum-pinned Gitleaks is installed in CI, and release provenance binds the exact commit, tag, package version, SBOM, notices, and checksums.",
        "Native package smoke: run 32823401864 built and launched exact candidate 5ee71fa on macOS arm64, Windows x64, and Linux x64. First starts were 2.098, 3.886, and 3.224 seconds; restarts were 2.440, 2.390, and 2.360 seconds; idle memory was 529.2, 488.1, and 498.5 MB. An additional isolated owner-Mac run passed at 0.991 seconds first start, 0.822 seconds restart, and 598.8 MB. All preserved their isolated synthetic database and enforced trust/maintenance boundaries. Retained evidence binds desktop/backend/log hashes. The packages were unsigned, unpublished, and not retained as installers; signing and lifecycle acceptance remain required. macOS x64/Intel is owner-deferred.",
        "Secrets: Gitleaks scanned the complete cleaned Git history and the staged remediation diff with no leaks. No real statements, databases, tokens, keys, or customer screenshots are tracked.",
        "Recovery: empty database bootstrap, schema-revision backup, retained daily/weekly backups, restore-on-copy, upgrade, rollback, and license offline-grace tests pass.",
        "Payment: test-mode replay, amount/currency mismatch, invalid signature, unauthenticated checkout, device limit, deactivation, and resend behavior pass after provider credentials are available.",
        "Privacy: app data remains local; sponsor card is static/non-personalized; behavior insights are never used for consequential decisions; pilot remains off unless separately approved.",
    ):
        add_list_item(document, item, check_num)
    add_callout(
        document,
        "CI RELEASE GATE",
        "Beta website candidate c93c7fc passed all seven jobs in GitHub Actions run 33382231788, including the full backend suite, supply-chain and full-history secret checks, desktop audits, deterministic media checks, website/browser matrices, Chromium/Firefox/WebKit app accessibility, and the clean 12-migration Supabase database matrix. Return the repository to PRIVATE after the final documentation-only CI run. Any later application, workflow, lockfile, generated-asset, or verification-contract change requires a new exact-SHA green run before tagging; source CI does not replace signed-package, provider, legal, or launch authorization gates.",
        tone="good",
    )
    document.add_heading("13.1 Preserve the verified private CI gate", level=2)
    for item in (
        "Retain https://github.com/oculusrex14/GODFIN/actions/runs/33382231788 as exact-source evidence for commit c93c7fcd1f520f017e4f8e6b1241f49eff9fbbcc. All seven jobs completed successfully on 31 August 2026.",
        "Keep oculusrex14/GODFIN PRIVATE. Confirm visibility before every tag or draft-release operation; do not paste repository credentials or billing information into evidence.",
        "If any application code, workflow, dependency lock, generated asset, or verification contract changes, push the cohesive change and wait for a new all-green run on that exact SHA.",
        "Check that backend, frontend, website, website-browser-matrix, desktop-audit, e2e, and supabase-db all execute real steps. A skipped or cancelled required job is not a pass.",
        "Keep checkout, deployment promotion, release publishing, and update-feed promotion disabled until their separate provider, signed-package, legal, and owner gates are complete.",
    ):
        add_list_item(document, item, decimal_num)
    add_source(document, "Exact beta website CI run", "https://github.com/oculusrex14/GODFIN/actions/runs/33382231788")
    add_source(document, "GitHub repository visibility", "https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/managing-repository-settings/setting-repository-visibility")
    add_owner_fields(document, ["Release commit", "CI run URL", "Security scan evidence", "Completed by / date"])

    document.add_heading("14. Prepare the private draft release", level=1)
    for item in (
        "Choose an immutable semantic candidate tag that matches the desktop package version exactly, such as v0.1.0. The release workflow intentionally accepts only vX.Y.Z tags; do not use an -rc suffix unless the validated workflow contract is deliberately changed first.",
        "Push the exact candidate commit to the private repository and wait for every CI job to pass.",
        "Confirm all required Apple, Windows, and R2 secrets exist in GitHub Actions without revealing values.",
        "Create and push the annotated tag. The release workflow verifies exact tag/commit/version agreement, refuses an existing release for that tag, builds the currently approved macOS arm64, Windows x64, and Linux x64 artifacts, verifies packages, generates SHA-256 checksums, SBOM, notices, and provenance, and creates a private draft GitHub Release. Keep macOS x64/Intel out of release claims until its deferred acceptance is reopened and passes.",
        "Confirm supply-chain/legal-clearance.json is approved. The workflow must remain fail-closed while legal status is pending or the recorded evidence hashes do not match.",
        "Review the draft only. Do not publish it. Download every artifact, verify checksums/signatures, and complete Section 12.",
        "Attach the final privacy-safe screenshots and private demo to internal review, not to a public release, until the owner approves.",
        "Record known limitations honestly: HDFC launch parser scope where applicable, live-market provider coverage, no recurring AI allowance, optional local/BYO AI, and external-service dependencies.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Private draft release exists and is not published.",
        "Every expected OS/architecture artifact and update manifest exists.",
        "Checksums, signatures, notarization, fuses, and clean-system evidence pass.",
        "Release notes match the shared entitlement manifest.",
        "No public updater promotion has run.",
    ):
        add_list_item(document, item, check_num)
    add_owner_fields(document, ["Candidate tag", "Draft release URL", "Release reviewer", "Completed by / date"])

    document.add_heading("15. Final website and support acceptance", level=1)
    add_callout(
        document,
        "VERIFIED ASSETS",
        "The current website tour demonstrates imports, learned classification, goals, recurring detection, CA tax packs, and local privacy using synthetic-data captures from the real React application. A muted WebM/MP4 loop, still posters, lazy loading, and prefers-reduced-motion fallbacks are included.",
        tone="good",
    )
    for item in (
        "Verify all advertised features are marked released in shared/entitlements.json and pass app acceptance tests. Hide anything unreleased.",
        "Review the final real screenshots captured from synthetic data. Confirm there are no real names, account numbers, emails, amounts from a real person, or provider keys.",
        "Play the private demo end-to-end. Verify it reflects the signed candidate and does not expose local paths, notifications, credentials, or personal data.",
        "Complete Google sign-in, double-opt-in waitlist, test/live checkout, license email, account activations, device deactivation, and download links on the canonical domain.",
        "Ensure Pro ₹4,999 and Max ₹9,999 are lifetime licenses with zero hosted credits; local AI and BYO keys consume no GODFIN credits; no hosted AI credit packs are currently sold.",
        "Review privacy, terms, refund, lifetime definition, device limit, offline grace, supported OS/banks, market-data caveats, and support contacts with qualified Indian legal/tax advisers.",
        "Assign launch-day monitoring for checkout failures, webhook retries, email delivery, downloads, license activation, support, refunds, security reports, and rollback.",
    ):
        add_list_item(document, item, decimal_num)
    for item in (
        "Website production paths and security headers pass.",
        "All sold features are implemented and released.",
        "Support and privacy mailboxes are staffed.",
        "Legal/tax/privacy approvals are archived.",
        "Signed downloads and account/device controls work.",
        "Screenshots and demo match the final candidate.",
    ):
        add_list_item(document, item, check_num)

    document.add_page_break()
    document.add_heading("16. Explicit public-launch gate", level=1)
    add_callout(
        document,
        "NO IMPLIED AUTHORIZATION",
        "A green build, deployed website, signed installer, draft release, completed runbook, or successful payment test does not authorize a public launch. Public release and Phase 6 require explicit written owner authorization.",
        tone="risk",
    )
    add_table(
        document,
        ["Gate", "Owner", "Complete", "Evidence / approval reference"],
        [
            ["Google OAuth callback", "Codex", "☒", "Production callback passed twice on 30 Jul 2026; rotated client active; original client revoked."],
            ["Second-account isolation", "", "☐", "Repeat with a distinct Google test account before public launch."],
            ["Desktop Gmail OAuth + sync", "Owner", "☐", "Install 5ee71fa or a documentation-only descendant, then complete fresh read-only authorization, sync, restart, disconnect, reconnect, and seven-day soak."],
            ["Supabase recovery + Auth hardening", "Owner", "☐", "Provide a recoverable backup or PITR, complete a restore drill, enable leaked-password protection if available, and retain evidence."],
            ["Dependency license clearance", "", "☐", "Human approval of conditional licenses with unchanged SBOM/notices hashes."],
            ["Cashfree + webhook + refund/tax", "Owner", "☐", "KYC and whitelisting are owner-confirmed. Add credentials privately, then retain sandbox/live webhook, refund, dispute, invoice, and tax evidence."],
            ["Resend + DNS + support inboxes", "Owner", "☐", "Resend domain, DKIM/SPF, encrypted Vercel variables, production double opt-in, and welcome-email queueing pass. DMARC, inbound reply, second-provider delivery, inbox monitoring, and support ownership remain."],
            ["Canonical domain + security headers", "Codex", "☒", "Production deployment dpl_D7W9Gk172WWmM4zyxz7vJhkgK9do serves godfin.dev; HSTS/CSP and media ranges verified; production Playwright passed 24/24 across Chromium, Firefox, and WebKit; public checkout remains disabled."],
            ["License custody + three devices", "", "☐", ""],
            ["macOS/Windows signing", "", "☐", ""],
            ["R2 updates + rollback", "", "☐", ""],
            ["Exact-candidate required-platform smoke", "Codex", "☒", "Run 32823401864 passed on macOS arm64, Windows x64, and Linux x64 with retained exact-SHA evidence. Packages are unsigned/unpublished smoke artifacts."],
            ["Signed clean-system lifecycle matrix", "", "☐", "Apple Silicon, Windows 10/11 x64, and Ubuntu 22.04+ remain external signed-installer gates. macOS x64/Intel is owner-deferred."],
            ["Browser-family matrix", "", "☐", "Chrome, Safari, Firefox, and Edge acceptance evidence remains deferred."],
            ["GitHub Actions + repository privacy", "Codex", "☐", "Run 33382231788 passed on exact SHA c93c7fc; final documentation CI must pass before the GitHub API is used to return oculusrex14/GODFIN to PRIVATE."],
            ["Security/privacy/recovery matrix", "", "☐", ""],
            ["Legal/tax/privacy review", "", "☐", ""],
            ["Private draft + screenshots + demo", "", "☐", ""],
            ["Final public-launch authorization", "", "☐", ""],
        ],
        [3300, 1300, 1100, 3660],
    )
    add_owner_fields(
        document,
        [
            "Authorized release version",
            "Authorized canonical website",
            "Authorized public release date/time",
            "Owner’s written authorization reference",
            "Owner signature",
            "Date",
        ],
    )
    final = document.add_paragraph()
    final.alignment = WD_ALIGN_PARAGRAPH.CENTER
    final.paragraph_format.space_before = Pt(20)
    set_run_font(
        final.add_run(
            "Only after this gate is signed may the team publish the GitHub Release, promote the update feed, enable production checkout, announce the product publicly, or begin Phase 6 growth work."
        ),
        size=11,
        color=RED,
        bold=True,
    )

    document.core_properties.title = "GODFIN Owner Completion Runbook"
    document.core_properties.subject = "Private launch readiness and owner-controlled completion gates"
    document.core_properties.author = "GODFIN"
    document.core_properties.keywords = "GODFIN, private launch, owner runbook, signing, Cashfree payments, privacy"
    document.core_properties.comments = ""
    return document


if __name__ == "__main__":
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    build_document().save(OUTPUT)
    print(OUTPUT)
