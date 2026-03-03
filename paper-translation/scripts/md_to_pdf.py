"""
Markdown → PDF 범용 변환 스크립트
(reportlab + NanumGothic + matplotlib mathtext 수식 렌더링)

사용법:
    python scripts/md_to_pdf.py --input output/{paper_id}/translation_ko.md \
                                --output output/{paper_id}/{paper_id}_번역.pdf
"""
import re
import sys
import argparse
from pathlib import Path
from io import BytesIO

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
    Table, TableStyle, Image, KeepTogether,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── 폰트 등록 ──────────────────────────────────────────────────────────────
import platform, sys as _sys
if platform.system() == "Windows":
    FONT_DIR = Path("C:/Windows/Fonts")
else:
    # Linux (Railway, Render 등): nixpacks로 설치된 NanumGothic 경로
    _candidates = [
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/NanumGothic.ttf"),
    ]
    FONT_DIR = next((p.parent for p in _candidates if p.exists()), Path("/usr/share/fonts"))
pdfmetrics.registerFont(TTFont("NanumGothic",     str(FONT_DIR / "NanumGothic.ttf")))
pdfmetrics.registerFont(TTFont("NanumGothicBold", str(FONT_DIR / "NanumGothicBold.ttf")))
BASE_FONT = "NanumGothic"
BOLD_FONT = "NanumGothicBold"

PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 5 * cm   # 좌우 여백 각 2.5cm

# ── LaTeX → 유니코드 (인라인 수식) ────────────────────────────────────────
LATEX_UNICODE = {
    # 소문자 그리스 문자
    r"\alpha": "α", r"\beta": "β", r"\gamma": "γ", r"\delta": "δ",
    r"\epsilon": "ε", r"\varepsilon": "ε", r"\zeta": "ζ", r"\eta": "η",
    r"\theta": "θ", r"\iota": "ι", r"\kappa": "κ", r"\lambda": "λ",
    r"\mu": "μ", r"\nu": "ν", r"\xi": "ξ", r"\pi": "π", r"\rho": "ρ",
    r"\sigma": "σ", r"\tau": "τ", r"\upsilon": "υ", r"\phi": "φ",
    r"\varphi": "φ", r"\chi": "χ", r"\psi": "ψ", r"\omega": "ω",
    # 대문자 그리스 문자
    r"\Gamma": "Γ", r"\Delta": "Δ", r"\Theta": "Θ", r"\Lambda": "Λ",
    r"\Xi": "Ξ", r"\Pi": "Π", r"\Sigma": "Σ", r"\Phi": "Φ",
    r"\Psi": "Ψ", r"\Omega": "Ω",
    # 연산자 / 관계 기호
    r"\geq": "≥", r"\leq": "≤", r"\neq": "≠", r"\approx": "≈",
    r"\equiv": "≡", r"\sim": "∼", r"\propto": "∝",
    r"\in": "∈", r"\notin": "∉", r"\subset": "⊂", r"\subseteq": "⊆",
    r"\cup": "∪", r"\cap": "∩", r"\emptyset": "∅",
    r"\infty": "∞", r"\partial": "∂", r"\nabla": "∇",
    r"\sum": "Σ", r"\prod": "Π", r"\int": "∫",
    r"\times": "×", r"\cdot": "·", r"\pm": "±", r"\mp": "∓",
    r"\rightarrow": "→", r"\leftarrow": "←", r"\leftrightarrow": "↔",
    r"\Rightarrow": "⇒", r"\Leftarrow": "⇐", r"\Leftrightarrow": "⟺",
    r"\forall": "∀", r"\exists": "∃", r"\neg": "¬",
    r"\mathbb{R}": "ℝ", r"\mathbb{N}": "ℕ", r"\mathbb{Z}": "ℤ",
    r"\mathcal{E}": "ℰ", r"\mathcal{D}": "𝒟", r"\mathcal{Q}": "𝒬",
    # 함수명
    r"\min": "min", r"\max": "max", r"\sup": "sup", r"\inf": "inf",
    r"\arg": "arg", r"\lim": "lim", r"\exp": "exp", r"\log": "log",
    r"\sin": "sin", r"\cos": "cos", r"\tan": "tan",
    r"\Pr": "Pr", r"\mathbb{E}": "E",
    # 기타
    r"\mid": " | ", r"\ldots": "…", r"\cdots": "⋯",
    r"\quad": "  ", r"\qquad": "    ",
    r"\left\{": "{", r"\right\}": "}",
    r"\left": "", r"\right": "",
    r"\bigl": "", r"\bigr": "", r"\big": "",
    r"\Bigl": "", r"\Bigr": "", r"\Big": "",
    r"\top": "⊤", r"\bot": "⊥",
    r"\mathbf": "", r"\mathrm": "", r"\mathit": "",
    r"\hat{x}": "x̂", r"\bar{x}": "x̄",
    r"\ell": "ℓ",
}

# 아래첨자 유니코드
_SUB = {**{str(i): chr(0x2080 + i) for i in range(10)},
        "a": "ₐ", "e": "ₑ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
        "n": "ₙ", "o": "ₒ", "p": "ₚ", "u": "ᵤ", "x": "ₓ",
        "m": "ₘ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "v": "ᵥ"}
# 위첨자 유니코드
_SUP = {"0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
        "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
        "+": "⁺", "-": "⁻", "T": "ᵀ", "n": "ⁿ", "*": "∗",
        "Δ": "Δ", "D": "ᴰ"}


def _conv(char_map: dict, s: str) -> str:
    return "".join(char_map.get(c, c) for c in s)


def latex_to_unicode(formula: str) -> str:
    """LaTeX 인라인 수식 → 유니코드 텍스트 변환."""
    s = formula

    # \text{...} → 일반 텍스트
    s = re.sub(r"\\(?:text|mathrm|mathbf|mathit)\{([^}]*)\}", r"\1", s)

    # \frac{a}{b} → (a/b)
    def frac_sub(m):
        n, d = m.group(1).strip(), m.group(2).strip()
        return f"({n}/{d})"
    for _ in range(3):          # 중첩 분수 처리
        s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", frac_sub, s)

    # \sqrt{a} → √a
    s = re.sub(r"\\sqrt\{([^}]*)\}", r"√(\1)", s)

    # LaTeX 명령어 → 유니코드
    for cmd, uni in LATEX_UNICODE.items():
        s = s.replace(cmd, uni)

    # _{...} 또는 _x
    def sub_repl(m):
        content = m.group(1) or m.group(2) or ""
        return _conv(_SUB, content)
    s = re.sub(r"_\{([^}]*)\}|_([A-Za-z0-9])", sub_repl, s)

    # ^{...} 또는 ^x
    def sup_repl(m):
        content = m.group(1) or m.group(2) or ""
        return _conv(_SUP, content)
    s = re.sub(r"\^\{([^}]*)\}|\^([A-Za-z0-9+\-∗Δ])", sup_repl, s)

    # 남은 중괄호 제거
    s = s.replace("{", "").replace("}", "")
    # 공백 정리
    s = re.sub(r" {2,}", " ", s).strip()
    return s


# ── 디스플레이 수식 → 이미지 (matplotlib mathtext) ────────────────────────
def _mpl_formula(formula: str) -> str:
    """LaTeX 수식을 matplotlib mathtext 호환 형식으로 정규화."""
    s = formula
    # \text{} → \mathrm{}
    s = re.sub(r"\\text\{([^}]*)\}", r"\\mathrm{\1}", s)
    # \mathbb{R} 등 처리
    s = s.replace(r"\mathbb{R}", r"\mathbb{R}")
    # 가끔 문제 되는 것들
    s = s.replace(r"\bigl", "").replace(r"\bigr", "")
    s = s.replace(r"\Bigl", "").replace(r"\Bigr", "")
    s = s.replace(r"\big", "").replace(r"\Big", "")
    s = s.replace(r"\left\{", r"\{").replace(r"\right\}", r"\}")
    s = s.replace(r"\left", "").replace(r"\right", "")
    return s


def render_display_math(formula: str, font_size: float = 12, dpi: int = 150):
    """Display 수식을 matplotlib mathtext로 렌더링 → BytesIO(PNG). 실패 시 None."""
    mpl_f = _mpl_formula(formula)
    try:
        fig = plt.figure(figsize=(8, 1))
        fig.patch.set_facecolor("white")
        t = fig.text(0.5, 0.5, f"${mpl_f}$",
                     ha="center", va="center",
                     fontsize=font_size, color="black")

        renderer = fig.canvas.get_renderer()
        bb = t.get_window_extent(renderer=renderer)
        w_in = max(bb.width / dpi + 0.5, 1.5)
        h_in = max(bb.height / dpi + 0.3, 0.35)
        fig.set_size_inches(w_in, h_in)

        buf = BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                    pad_inches=0.08, facecolor="white")
        plt.close(fig)
        buf.seek(0)
        return buf
    except Exception:
        plt.close("all")
        return None


def math_image_flowable(formula: str, max_w: float = CONTENT_W):
    """수식 이미지를 ReportLab Image flowable로 반환. 실패 시 Paragraph(text) 반환."""
    buf = render_display_math(formula)
    if buf is None:
        fallback = latex_to_unicode(formula)
        return Paragraph(
            fallback,
            ParagraphStyle("math_fb", fontName=BASE_FONT, fontSize=10,
                           leading=16, alignment=TA_CENTER,
                           textColor=colors.HexColor("#333333")),
        )
    img = Image(buf)
    # 비율 유지하며 최대 너비 제한
    if img.drawWidth > max_w:
        scale = max_w / img.drawWidth
        img.drawWidth  *= scale
        img.drawHeight *= scale
    return img


# ── 스타일 정의 ──────────────────────────────────────────────────────────
def make_styles(font_boost: float = 0):
    s = {}
    common = dict(fontName=BASE_FONT, spaceBefore=6, spaceAfter=8, leading=22 + font_boost)

    s["h1"] = ParagraphStyle(
        "h1", fontName=BOLD_FONT, fontSize=18 + font_boost, leading=28 + font_boost,
        spaceBefore=20, spaceAfter=12,
        textColor=colors.HexColor("#1a3a5c"), alignment=TA_CENTER,
    )
    s["h2"] = ParagraphStyle(
        "h2", fontName=BOLD_FONT, fontSize=14 + font_boost, leading=22 + font_boost,
        spaceBefore=18, spaceAfter=8,
        textColor=colors.HexColor("#1a3a5c"),
    )
    s["h3"] = ParagraphStyle(
        "h3", fontName=BOLD_FONT, fontSize=11.5 + font_boost, leading=20 + font_boost,
        spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor("#2c5f8a"),
    )
    s["body"] = ParagraphStyle(
        "body", **common, fontSize=10 + font_boost, alignment=TA_JUSTIFY,
    )
    s["bullet"] = ParagraphStyle(
        "bullet", fontName=BASE_FONT, fontSize=10 + font_boost, leading=20 + font_boost,
        leftIndent=18, firstLineIndent=0, bulletIndent=6,
        spaceBefore=4, spaceAfter=4,
    )
    s["sub_bullet"] = ParagraphStyle(
        "sub_bullet", fontName=BASE_FONT, fontSize=9.5 + font_boost, leading=18 + font_boost,
        leftIndent=36, firstLineIndent=0, bulletIndent=24,
        spaceBefore=3, spaceAfter=3,
    )
    s["code"] = ParagraphStyle(
        "code", fontName="Courier", fontSize=8.5 + font_boost, leading=14 + font_boost,
        leftIndent=20, spaceBefore=6, spaceAfter=6,
        backColor=colors.HexColor("#f4f4f4"),
    )
    s["quote"] = ParagraphStyle(
        "quote", fontName=BASE_FONT, fontSize=9.5 + font_boost, leading=18 + font_boost,
        leftIndent=24, spaceBefore=6, spaceAfter=6,
        textColor=colors.HexColor("#444444"),
    )
    s["table_h"] = ParagraphStyle(
        "table_h", fontName=BOLD_FONT, fontSize=9 + font_boost,
        leading=13 + font_boost, alignment=TA_CENTER,
    )
    s["table_c"] = ParagraphStyle(
        "table_c", fontName=BASE_FONT, fontSize=9 + font_boost,
        leading=13 + font_boost, alignment=TA_LEFT,
    )
    s["math_center"] = ParagraphStyle(
        "math_center", fontName=BASE_FONT, fontSize=10 + font_boost, leading=18 + font_boost,
        alignment=TA_CENTER, spaceBefore=10, spaceAfter=10,
        textColor=colors.HexColor("#1a1a1a"),
    )
    return s


# ── 인라인 마크업 처리 ───────────────────────────────────────────────────
# ReportLab Paragraph XML에서 허용되는 태그 목록
_RL_ALLOWED_TAG = re.compile(
    r"</?(?:b|i|u|super|sub|font|strike|a|br)(?:\s[^>]*)?>",
    re.IGNORECASE,
)


def inline(text: str) -> str:
    """**bold**, *italic*, `code`, 인라인 수식($...$) → reportlab XML 태그."""

    # HTML <sup>/<sub> → ReportLab <super>/<sub> (번역 결과의 각주 표기 처리)
    text = re.sub(r"<sup>(.*?)</sup>", r"<super>\1</super>",
                  text, flags=re.IGNORECASE | re.DOTALL)

    # ReportLab 허용 태그 이외의 < > 이스케이프
    # (닫히지 않은 HTML 태그 등으로 인한 XML 파싱 오류 방지)
    segs: list[str] = []
    last = 0
    for m in _RL_ALLOWED_TAG.finditer(text):
        segs.append(text[last:m.start()].replace("<", "&lt;").replace(">", "&gt;"))
        segs.append(m.group(0))
        last = m.end()
    segs.append(text[last:].replace("<", "&lt;").replace(">", "&gt;"))
    text = "".join(segs)

    # 인라인 수식 먼저 변환 (이미지 삽입 불가 → 유니코드 텍스트)
    def math_sub(m):
        return f"<i>{latex_to_unicode(m.group(1))}</i>"
    text = re.sub(r"\$([^$]+?)\$", math_sub, text)

    # bold
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    # italic (이미 i 태그 있으면 중복 방지)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    # inline code
    text = re.sub(r"`(.+?)`", r'<font name="Courier">\1</font>', text)
    # & 이스케이프 (기존 XML 엔티티 제외)
    text = re.sub(r"&(?!amp;|lt;|gt;|quot;|#\d+;)", "&amp;", text)
    return text


# ── 마크다운 파싱 ────────────────────────────────────────────────────────
def parse_md(md_path: Path, styles: dict):
    story = []
    lines = md_path.read_text(encoding="utf-8").splitlines()

    in_code   = False
    code_buf  = []
    in_table  = False
    table_rows = []

    def flush_table():
        nonlocal in_table, table_rows
        if not table_rows:
            return
        # 구분선 행 제거
        rows = [r for r in table_rows if r is not None]
        if not rows:
            table_rows = []
            in_table = False
            return

        col_n = max(len(r) for r in rows)

        def cell(text, style):
            return Paragraph(inline(text.strip()), style)

        tdata = []
        for ri, row in enumerate(rows):
            padded = (row + [""] * col_n)[:col_n]
            st = styles["table_h"] if ri == 0 else styles["table_c"]
            tdata.append([cell(c, st) for c in padded])

        col_w = CONTENT_W / col_n
        tbl = Table(tdata, colWidths=[col_w] * col_n, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0), (-1, 0),  colors.HexColor("#1a3a5c")),
            ("TEXTCOLOR",      (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",       (0, 0), (-1, 0),  BOLD_FONT),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#eef2f7")]),
            ("GRID",           (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
            ("VALIGN",         (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING",     (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0), (-1, -1), 5),
        ]))
        story.append(Spacer(1, 8))
        story.append(tbl)
        story.append(Spacer(1, 8))
        table_rows = []
        in_table = False

    i = 0
    while i < len(lines):
        line     = lines[i]
        stripped = line.strip()

        # ── 코드 블록 ──────────────────────────────────────────────────
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
                code_buf = []
            else:
                in_code = False
                for cl in code_buf:
                    txt = cl.replace("&", "&amp;").replace("<", "&lt;") \
                             .replace(">", "&gt;").replace(" ", "\u00a0")
                    story.append(Paragraph(txt, styles["code"]))
                story.append(Spacer(1, 4))
            i += 1
            continue

        if in_code:
            code_buf.append(line)
            i += 1
            continue

        # ── 표 ─────────────────────────────────────────────────────────
        if stripped.startswith("|"):
            if not in_table:
                in_table = True
                table_rows = []
            cols = [c for c in stripped.split("|") if c != ""]
            if all(re.match(r"^[-: ]+$", c) for c in cols):
                table_rows.append(None)          # 구분선
            else:
                table_rows.append(cols)
            i += 1
            continue
        elif in_table:
            flush_table()

        # ── 빈 줄 ──────────────────────────────────────────────────────
        if not stripped:
            story.append(Spacer(1, 8))
            i += 1
            continue

        # ── 수평선 ─────────────────────────────────────────────────────
        if re.match(r"^-{3,}$", stripped):
            story.append(Spacer(1, 4))
            story.append(HRFlowable(
                width="100%", thickness=0.8,
                color=colors.HexColor("#aaaaaa"), spaceAfter=8,
            ))
            i += 1
            continue

        # ── Display 수식 블록 ($$...$$) ──────────────────────────────
        if stripped == "$$":
            math_lines = []
            i += 1
            while i < len(lines) and lines[i].strip() != "$$":
                math_lines.append(lines[i].strip())
                i += 1
            i += 1   # 닫는 $$
            formula = " ".join(math_lines)
            story.append(Spacer(1, 6))
            story.append(math_image_flowable(formula))
            story.append(Spacer(1, 6))
            continue

        # 같은 줄에 $$ 열고 닫는 경우
        m_disp = re.match(r"^\$\$(.+?)\$\$$", stripped)
        if m_disp:
            formula = m_disp.group(1).strip()
            story.append(Spacer(1, 6))
            story.append(math_image_flowable(formula))
            story.append(Spacer(1, 6))
            i += 1
            continue

        # ── 제목 ───────────────────────────────────────────────────────
        if re.match(r"^# [^#]", stripped):
            story.append(Spacer(1, 12))
            story.append(Paragraph(inline(stripped[2:]), styles["h1"]))
            story.append(HRFlowable(
                width="100%", thickness=1.5,
                color=colors.HexColor("#1a3a5c"), spaceAfter=10,
            ))
            i += 1
            continue

        if stripped.startswith("## "):
            story.append(Spacer(1, 10))
            story.append(Paragraph(inline(stripped[3:]), styles["h2"]))
            story.append(HRFlowable(
                width="100%", thickness=0.6,
                color=colors.HexColor("#2c5f8a"), spaceAfter=6,
            ))
            i += 1
            continue

        if stripped.startswith("### "):
            story.append(Paragraph(inline(stripped[4:]), styles["h3"]))
            i += 1
            continue

        # ── 인용 ───────────────────────────────────────────────────────
        if stripped.startswith("> "):
            story.append(Paragraph(inline(stripped[2:]), styles["quote"]))
            i += 1
            continue

        # ── 글머리 기호 ────────────────────────────────────────────────
        if re.match(r"^[-*] ", stripped):
            text = re.sub(r"^[-*] ", "", stripped)
            story.append(Paragraph("• " + inline(text), styles["bullet"]))
            i += 1
            continue

        if re.match(r"^\s{2,}[-*] ", line):
            text = re.sub(r"^\s+[-*] ", "", line)
            story.append(Paragraph("◦ " + inline(text), styles["sub_bullet"]))
            i += 1
            continue

        # ── 번호 목록 ──────────────────────────────────────────────────
        m_ol = re.match(r"^(\d+)\.\s+(.*)", stripped)
        if m_ol:
            story.append(
                Paragraph(f"{m_ol.group(1)}. " + inline(m_ol.group(2)),
                          styles["bullet"])
            )
            i += 1
            continue

        # ── 일반 본문 ──────────────────────────────────────────────────
        story.append(Paragraph(inline(stripped), styles["body"]))
        i += 1

    if in_table:
        flush_table()

    return story


# ── 페이지 헤더/푸터 ─────────────────────────────────────────────────────
FOOTER_TEXT = ""   # 호출 시 동적으로 설정됨


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont(BASE_FONT, 8)
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.drawCentredString(
        PAGE_W / 2, 1.2 * cm,
        f"{FOOTER_TEXT}  |  {doc.page}",
    )
    canvas.restoreState()


# ── 메인 ────────────────────────────────────────────────────────────────
def main():
    global FOOTER_TEXT

    parser = argparse.ArgumentParser(description="Markdown → PDF (Korean + Math)")
    parser.add_argument("--input",      required=True,  help="입력 .md 파일 경로")
    parser.add_argument("--output",     required=True,  help="출력 .pdf 파일 경로")
    parser.add_argument("--title",      default="",     help="PDF 제목 (선택)")
    parser.add_argument("--author",     default="",     help="PDF 저자 (선택)")
    parser.add_argument("--footer",     default="",     help="푸터 텍스트 (선택)")
    parser.add_argument("--font-boost", type=float, default=0, help="전체 폰트 크기 증가량 (pt)")
    args = parser.parse_args()

    md_path  = Path(args.input)
    pdf_path = Path(args.output)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    # 푸터: 인자 없으면 md 파일명 사용
    FOOTER_TEXT = args.footer if args.footer else md_path.stem

    styles = make_styles(font_boost=args.font_boost)
    story  = parse_md(md_path, styles)

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        topMargin=2.5 * cm,  bottomMargin=2.5 * cm,
        title=args.title   or md_path.stem,
        author=args.author or "",
    )
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF 생성 완료: {pdf_path}")


if __name__ == "__main__":
    main()
