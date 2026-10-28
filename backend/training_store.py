# -*- coding: utf-8 -*-
"""训练文件库（第 175/176 轮）——重点训练「生产的文件」，而非仅文本。

自包含模块，不 import app.py / flask。职责：
1. desensitize_text        —— 个人信息脱敏（姓名/院校/电话/邮箱/学号/组织名）
2. extract_structure       —— 提取成品文件的结构特征（docx/pptx/pdf/zip）
3. archive_training_file   —— 复制成品文件入训练库 + 写 .meta.json
4. list_training_stats     —— 训练库统计（总份数 / 按赛事 / 按类型）

版权红线：只归档自建原创/经人工确认的结构示范，禁止复制获奖原文段落。
"""
import datetime
import json
import os
import re
import shutil
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAIN_DIR = os.path.join(REPO_ROOT, "backend", "assets", "训练库")

# ---- 脱敏正则（保守、不误伤官方赛事名/泛化词）----
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
_ID_RE = re.compile(r"(?<!\d)(\d{17}[\dXx])(?!\d)")           # 身份证 18 位
_STUDENT_RE = re.compile(r"(?<!\d)(20\d{2}\d{4,8})(?!\d)")    # 学号：20 开头 10-14 位


def desensitize_text(text):
    """个人信息脱敏，返回新字符串；空值原样返回。"""
    if not text:
        return text
    t = _EMAIL_RE.sub("xxx@example.com", text)
    t = _PHONE_RE.sub("138****0000", t)
    t = _ID_RE.sub("110***********0000", t)
    t = _STUDENT_RE.sub("20******0000", t)
    # 指导教师/负责人/队长/成员 后跟的中文人名 → 某同学
    t = re.sub(r"(指导老师|指导教师|负责人|队长|成员)[：:]\s*[\u4e00-\u9fa5]{2,4}",
               r"\1：某同学", t)
    # 院校：XX大学/XX学院 → 某高校（不碰「大学生」「大学城」等泛化词）
    t = re.sub(r"(?<![生城])[\u4e00-\u9fa5]{2,8}(大学|学院)", "某高校", t)
    return t


def _load_docx(path):
    try:
        from docx import Document
        return Document(path)
    except Exception:
        return None


def _load_pptx(path):
    try:
        from pptx import Presentation
        return Presentation(path)
    except Exception:
        return None


def extract_structure(path, artifact_type):
    """提取结构特征。artifact_type ∈ {docx, pptx, pdf, zip}。"""
    st = {
        "artifact_type": artifact_type,
        "file_size": os.path.getsize(path) if os.path.exists(path) else 0,
    }
    at = (artifact_type or "").lower()
    if at == "docx":
        doc = _load_docx(path)
        if doc is None:
            st["error"] = "无法解析 docx"
            return st
        headings = [
            p.text.strip() for p in doc.paragraphs
            if p.style is not None and p.style.name is not None
            and p.style.name.startswith("Heading")
        ]
        toc = False
        try:
            xml = doc.element.xml
            toc = ("TOC" in xml) and ("instrText" in xml)
        except Exception:
            toc = False
        st.update({
            "headings": headings,
            "heading_count": len(headings),
            "toc_field": toc,
            "table_count": len(doc.tables),
            "char_count": sum(len(p.text) for p in doc.paragraphs),
        })
    elif at == "pptx":
        prs = _load_pptx(path)
        if prs is None:
            st["error"] = "无法解析 pptx"
            return st
        titles, notes_ok = [], 0
        for slide in prs.slides:
            t = slide.shapes.title.text.strip() if slide.shapes.title is not None else ""
            titles.append(t)
            try:
                if slide.has_notes_slide and slide.notes_slide.notes_text_frame.text.strip():
                    notes_ok += 1
            except Exception:
                pass
        st.update({
            "page_count": len(prs.slides),
            "titles": titles,
            "notes_count": notes_ok,
        })
    elif at == "pdf":
        try:
            from pypdf import PdfReader
        except Exception:
            try:
                from PyPDF2 import PdfReader
            except Exception:
                st["error"] = "无 pypdf/PyPDF2 依赖"
                return st
        try:
            r = PdfReader(path)
            st["page_count"] = len(r.pages)
        except Exception as e:
            st["error"] = f"pdf 解析失败：{e}"
    elif at == "zip":
        try:
            with zipfile.ZipFile(path) as z:
                names = [n for n in z.namelist() if not n.endswith("/")]
                st["module_list"] = names
                st["module_count"] = len(names)
        except Exception as e:
            st["error"] = f"zip 解析失败：{e}"
    else:
        st["error"] = f"未知产物类型：{artifact_type}"
    return st


def archive_training_file(src_path, competition, artifact_type, meta=None):
    """复制成品文件入训练库，写同名 .meta.json，返回归档后路径。

    meta 必填建议：来源、生成日期、赛事、产物类型、质检结果；结构特征自动补。
    """
    meta = dict(meta or {})
    if not os.path.exists(src_path):
        raise FileNotFoundError(src_path)
    comp = re.sub(r"[\\/:*?\"<>|\s]+", "_", str(competition or "通用"))
    at = (artifact_type or "file").lower()
    subdir = os.path.join(TRAIN_DIR, f"{comp}_{at}")
    os.makedirs(subdir, exist_ok=True)

    ext = os.path.splitext(src_path)[1] or ("." + at)
    base = re.sub(r"[^\w\u4e00-\u9fa5-]+", "_", os.path.splitext(os.path.basename(src_path))[0]) or "sample"
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(subdir, f"{base}_{stamp}{ext}")
    shutil.copy2(src_path, dest)

    structure = extract_structure(dest, at)
    record = {
        "来源": meta.get("来源", "AI生成·经人工确认·规范示范"),
        "生成日期": meta.get("生成日期", datetime.date.today().isoformat()),
        "赛事": competition,
        "产物类型": at,
        "质检结果": meta.get("质检结果", "待质检"),
        "脱敏标记": meta.get("脱敏标记", True),
        "文件大小": structure.get("file_size", os.path.getsize(dest)),
        "结构特征": structure,
    }
    with open(dest + ".meta.json", "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return dest


def list_training_stats():
    """统计训练库：总份数 + 按赛事 + 按类型。"""
    stats = {"总份数": 0, "by_competition": {}, "by_type": {}}
    if not os.path.isdir(TRAIN_DIR):
        return stats
    for root, _dirs, files in os.walk(TRAIN_DIR):
        for fn in files:
            if not fn.endswith(".meta.json"):
                continue
            mp = os.path.join(root, fn)
            try:
                rec = json.load(open(mp, encoding="utf-8"))
            except Exception:
                continue
            stats["总份数"] += 1
            comp = rec.get("赛事", "未知")
            at = rec.get("产物类型", "未知")
            stats["by_competition"][comp] = stats["by_competition"].get(comp, 0) + 1
            stats["by_type"][at] = stats["by_type"].get(at, 0) + 1
    return stats
